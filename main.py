
import os
import asyncio
import logging
import tempfile
from pathlib import Path

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("musicbot")


def search_tracks(query):
    results = []

    # SoundCloud qidiruvi
    try:
        options = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            data = ydl.extract_info(
                f"scsearch10:{query}",
                download=False
            )

        for item in (data or {}).get("entries", []):
            if not item:
                continue

            url = item.get("webpage_url") or item.get("url")
            if not url or not str(url).startswith("http"):
                continue

            results.append({
                "title": item.get("title", "Nomsiz qo‘shiq"),
                "url": url,
                "source": "SoundCloud",
            })
    except Exception:
        log.exception("SoundCloud qidiruvi ishlamadi")

    return results[:10]


def download_full_track(url, folder):
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(folder) / "track.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    files = [
        p for p in Path(folder).iterdir()
        if p.is_file() and p.suffix.lower() not in (".part", ".ytdl", ".json")
    ]

    if not files:
        raise FileNotFoundError("Audio fayl topilmadi")

    path = max(files, key=lambda p: p.stat().st_size)

    if path.stat().st_size < 1_000_000:
        raise RuntimeError(
            "Fayl juda qisqa bo‘lishi mumkin. To‘liq versiya topilmadi."
        )

    return str(path)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Qo‘shiq nomini yozing. To‘liq audio mavjud manbalardan qidiraman."
    )


async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if not name:
        return

    status = await update.message.reply_text("🔎 Qo‘shiq qidirilmoqda...")

    try:
        songs = await asyncio.to_thread(search_tracks, name)

        if not songs:
            await status.edit_text(
                "Natija topilmadi. Boshqa nom bilan urinib ko‘ring."
            )
            return

        context.user_data["songs"] = songs
        keyboard = []

        for i in range(0, len(songs), 2):
            row = []
            for j in range(i, min(i + 2, len(songs))):
                row.append(
                    InlineKeyboardButton(
                        f"{j + 1}. {songs[j]['title'][:30]}",
                        callback_data=f"song:{j}",
                    )
                )
            keyboard.append(row)

        await status.edit_text(
            "🎶 Natijani tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception:
        log.exception("Qidiruv xatosi")
        await status.edit_text("Qidiruvda xato yuz berdi.")


async def select_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        index = int(query.data.split(":")[1])
        song = context.user_data["songs"][index]
    except (ValueError, IndexError, KeyError):
        await query.message.reply_text("Qaytadan qidiring.")
        return

    status = await query.message.reply_text(
        f"⏳ Audio olinmoqda: {song['title']}"
    )

    try:
        with tempfile.TemporaryDirectory() as folder:
            path = await asyncio.to_thread(
                download_full_track, song["url"], folder
            )

            if Path(path).stat().st_size > 49 * 1024 * 1024:
                await status.edit_text(
                    "Fayl Telegramga yuborish uchun juda katta."
                )
                return

            with open(path, "rb") as audio:
                await query.message.reply_audio(
                    audio=audio,
                    title=song["title"][:64],
                    filename=Path(path).name,
                    read_timeout=120,
                    write_timeout=120,
                )

        await status.delete()

    except Exception:
        log.exception("To‘liq audio olinmadi")
        await status.edit_text(
            "❌ To‘liq versiyani bu manbadan olish imkoni bo‘lmadi. "
            "Boshqa natijani sinab ko‘ring."
        )


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN sozlanmagan")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(select_song, pattern=r"^song:\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))
    app.run_polling()


if __name__ == "__main__":
    main()
