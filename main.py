
import os
import re
import asyncio
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MAX_RESULTS = 20
MAX_UPLOAD = 49 * 1024 * 1024

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN Railway Variables ichida yo'q")

def is_url(text):
    try:
        u = urlparse(text.strip())
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False

def safe_name(name):
    return re.sub(r"[^a-zA-Z0-9._ -]", "_", name)[:100] or "media"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 MUSIQA BOT\n\n"
        "Qo'shiq nomini yozing — natijalarni chiqaraman.\n"
        "YouTube yoki Instagram havolasini yuboring — video yoki audio tanlang.\n\n"
        "Ovozli xabar orqali qidirish mavjud emas."
    )

async def search_music(query):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "noplaylist": True,
        "socket_timeout": 12,
    }
    def run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"ytsearch{MAX_RESULTS}:{query}", download=False)
    return await asyncio.to_thread(run)

async def download_media(url, audio=False):
    temp = tempfile.mkdtemp(prefix="musicbot_")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": str(Path(temp) / "%(title).80s.%(ext)s"),
        "socket_timeout": 20,
        "retries": 2,
        "max_filesize": MAX_UPLOAD,
        "format": "bestaudio/best" if audio else "best[filesize<49M]/best",
    }
    if audio:
        opts["format"] = "bestaudio[filesize<49M]/bestaudio"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    def run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info.get("title", "Media"), temp

    title, folder = await asyncio.to_thread(run)
    files = [p for p in Path(folder).iterdir() if p.is_file()]
    if not files:
        raise RuntimeError("Yuklangan fayl topilmadi")
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return title, files[0], folder

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if is_url(text):
        context.user_data["media_url"] = text
        keyboard = [[
            InlineKeyboardButton("📹 Video", callback_data="media:video"),
            InlineKeyboardButton("🎧 Audio", callback_data="media:audio"),
        ]]
        await update.message.reply_text(
            "Nimani yuklaymiz?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    msg = await update.message.reply_text("🔎 Qidirilmoqda...")
    try:
        data = await search_music(text)
        entries = (data or {}).get("entries") or []
        entries = [e for e in entries if e and e.get("id")]
        if not entries:
            await msg.edit_text("Natija topilmadi. Boshqa nom bilan urinib ko'ring.")
            return

        context.user_data["search_results"] = [
            {
                "title": (e.get("title") or "Nomsiz")[:100],
                "url": e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
                "duration": e.get("duration"),
            }
            for e in entries
        ]

        rows = []
        for i, e in enumerate(context.user_data["search_results"]):
            dur = e["duration"]
            duration = f" ({int(dur)//60}:{int(dur)%60:02d})" if dur else ""
            rows.append([InlineKeyboardButton(
                f"{i+1}. {e['title'][:55]}{duration}",
                callback_data=f"song:{i}"
            )])

        await msg.edit_text(
            f"🎵 {len(entries)} ta natija topildi. Keraklisini tanlang:",
            reply_markup=InlineKeyboardMarkup(rows)
        )
    except Exception:
        log.exception("Music search failed")
        await msg.edit_text("Qidirishda xato yuz berdi. Keyinroq qayta urinib ko'ring.")

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action.startswith("song:"):
        results = context.user_data.get("search_results", [])
        try:
            index = int(action.split(":")[1])
            song = results[index]
        except (ValueError, IndexError):
            await query.message.reply_text("Natijalar eskirgan. Qo'shiqni qayta qidiring.")
            return

        await query.message.reply_text(f"⏳ Yuklanmoqda: {song['title']}")
        try:
            title, path, folder = await download_media(song["url"], audio=True)
            try:
                if path.stat().st_size > MAX_UPLOAD:
                    await query.message.reply_text("Audio Telegram uchun juda katta.")
                    return
                with path.open("rb") as f:
                    await query.message.reply_audio(
                        audio=f, title=title[:64], read_timeout=60, write_timeout=60
                    )
            finally:
                import shutil
                shutil.rmtree(folder, ignore_errors=True)
        except Exception:
            log.exception("Audio download failed")
            await query.message.reply_text(
                "Audio yuklanmadi. Manba cheklangan yoki formatni olishning imkoni yo'q."
            )
        return

    if action in ("media:video", "media:audio"):
        url = context.user_data.get("media_url")
        if not url:
            await query.message.reply_text("Havolani qayta yuboring.")
            return
        audio = action.endswith("audio")
        await query.message.reply_text("⏳ Yuklanmoqda, biroz kuting...")
        try:
            title, path, folder = await download_media(url, audio=audio)
            try:
                if path.stat().st_size > MAX_UPLOAD:
                    await query.message.reply_text(
                        "Fayl juda katta. Kichikroq sifatdagi videoni tanlang."
                    )
                    return
                with path.open("rb") as f:
                    if audio:
                        await query.message.reply_audio(
                            audio=f, title=title[:64],
                            read_timeout=60, write_timeout=60
                        )
                    else:
                        await query.message.reply_video(
                            video=f, caption=title[:900],
                            read_timeout=60, write_timeout=60
                        )
            finally:
                import shutil
                shutil.rmtree(folder, ignore_errors=True)
        except Exception:
            log.exception("Media download failed")
            await query.message.reply_text(
                "Yuklash amalga oshmadi. Bu havola yoki format qo'llanmasligi mumkin."
            )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ovozli xabar orqali qidirish o'chirilgan.")

async def error_handler(update, context):
    log.error("Bot xatosi", exc_info=context.error)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_error_handler(error_handler)
    log.info("Telegram music bot ishga tushdi")
    app.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    main()
vv
