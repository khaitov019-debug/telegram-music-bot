
import os
import asyncio
import logging
import tempfile
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import yt_dlp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Railway Variables ichida TELEGRAM_BOT_TOKEN yo'q")

MAX_RESULTS = 20


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 MUSIQA BOTIGA XUSH KELIBSIZ!\n\n"
        "Qo‘shiq yoki ijrochi nomini yozing.\n"
        "Masalan: Eminem Mockingbird\n\n"
        "🎧 Natijalardan kerakli qo‘shiqni tanlang."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Qo‘shiq nomini yozing.\n"
        "Ro‘yxatdan keraklisini tanlang — bot audio yuborishga harakat qiladi."
    )


def search_music_sync(song_name):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 1,
    }

    results = []
    seen = set()

    # YouTube qidiruvi
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(
                "ytsearch20:" + song_name,
                download=False,
            )

        for item in (data or {}).get("entries") or []:
            if not item:
                continue

            video_id = item.get("id")
            title = item.get("title")

            if not video_id or not title:
                continue

            url = item.get("webpage_url")
            if not url:
                url = f"https://www.youtube.com/watch?v={video_id}"

            key = url
            if key in seen:
                continue

            seen.add(key)
            results.append({
                "title": title,
                "url": url,
            })

    except Exception:
        log.exception("YouTube qidiruv xatosi")

    return results[:MAX_RESULTS]


async def search_music(song_name):
    return await asyncio.to_thread(search_music_sync, song_name)


def download_audio_sync(url, folder):
    output = str(Path(folder) / "audio.%(ext)s")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 2,
        "extractor_retries": 2,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    for file in Path(folder).iterdir():
        if file.suffix.lower() == ".mp3":
            return str(file)

    raise FileNotFoundError(
        "MP3 topilmadi. Serverda FFmpeg o‘rnatilganini tekshiring."
    )


async def handle_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return

    song_name = update.message.text.strip()
    if not song_name:
        return

    status = await update.message.reply_text("🔎 Qo‘shiqlar qidirilmoqda...")

    try:
        results = await search_music(song_name)

        if not results:
            await status.edit_text(
                "😕 Qo‘shiq topilmadi.\nBoshqa nom bilan urinib ko‘ring."
            )
            return

        context.user_data["music_results"] = results

        # Har qatorda 2 ta qo‘shiq tugmasi
        keyboard = []

        for i in range(0, len(results), 2):
            row = []

            for j in range(i, min(i + 2, len(results))):
                title = results[j]["title"]

                if len(title) > 24:
                    title = title[:21] + "..."

                row.append(
                    InlineKeyboardButton(
                        f"{j + 1}. {title}",
                        callback_data=f"song:{j}",
                    )
                )

            keyboard.append(row)

        await status.edit_text(
            f"🎶 {len(results)} ta natija topildi.\n"
            "Kerakli qo‘shiqni tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception:
        log.exception("Qidiruv xatosi")
        await status.edit_text(
            "❌ Qidiruvda xato yuz berdi. Railway Logs'ni tekshiring."
        )


async def select_song(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    try:
        index = int(query.data.split(":")[1])
        results = context.user_data.get("music_results", [])

        if index < 0 or index >= len(results):
            await query.message.reply_text(
                "Ro‘yxat eskirgan. Qo‘shiq nomini qaytadan yuboring."
            )
            return

        item = results[index]
        title = item["title"]
        url = item["url"]

        status = await query.message.reply_text(
            f"⬇️ Yuklanmoqda:\n{title}"
        )

        with tempfile.TemporaryDirectory() as folder:
            path = await asyncio.to_thread(
                download_audio_sync,
                url,
                folder,
            )

            with open(path, "rb") as audio:
                await query.message.reply_audio(
                    audio=audio,
                    title=title[:64],
                    read_timeout=180,
                    write_timeout=180,
                    connect_timeout=30,
                )

        await status.edit_text("✅ Audio yuborildi!")

    except Exception:
        log.exception("Audio yuklash xatosi")
        await query.message.reply_text(
            "❌ Bu qo‘shiqni yuklab bo‘lmadi.\n"
            "Boshqa natijani tanlab ko‘ring."
        )


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    log.error(
        "Botda xato yuz berdi",
        exc_info=context.error,
    )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(
        CallbackQueryHandler(
            select_song,
            pattern=r"^song:\d+$",
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_search,
        )
    )

    app.add_error_handler(error_handler)

    log.info("Musiqa bot ishga tushmoqda...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
