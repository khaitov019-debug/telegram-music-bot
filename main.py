
import os
import re
import asyncio
import logging
import tempfile
from pathlib import Path
from urllib.parse import quote

import yt_dlp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MAX_RESULTS = 20


def search_songs_sync(query):
    """YouTube qidiruvidan 20 tagacha natija oladi."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        data = ydl.extract_info(
            f"ytsearch{MAX_RESULTS}:{query}",
            download=False,
        )

    songs = []

    for item in (data or {}).get("entries", []):
        if not item:
            continue

        video_id = item.get("id")
        title = item.get("title") or "Nomsiz qo‘shiq"

        if not video_id:
            webpage_url = item.get("webpage_url", "")
            match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", webpage_url)
            if match:
                video_id = match.group(1)

        if not video_id:
            continue

        songs.append({
            "title": title[:150],
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    return songs


def download_audio_sync(url, folder):
    """Tanlangan videodan MP3 audio tayyorlaydi."""
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(folder_path / "track.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    for file in folder_path.iterdir():
        if file.is_file() and file.suffix.lower() == ".mp3":
            return str(file)

    raise FileNotFoundError("MP3 audio fayl topilmadi")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Salom! Qo‘shiq nomi yoki ijrochi ismini yozing.\n\n"
        "Men 20 tagacha natija topishga harakat qilaman. "
        "Kerakli qo‘shiq tugmasini bossangiz, audio yuboriladi."
    )


async def search_songs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()

    if not query:
        return

    if len(query) > 200:
        await update.message.reply_text("Qidiruv matni juda uzun. Qisqaroq yozing.")
        return

    status = await update.message.reply_text("🔎 Qo‘shiqlar qidirilmoqda...")

    try:
        songs = await asyncio.to_thread(search_songs_sync, query)

        if not songs:
            await status.edit_text(
                "😕 Qo‘shiq topilmadi. Boshqa nom bilan urinib ko‘ring."
            )
            return

        # Natijalar ushbu foydalanuvchining sessiyasida saqlanadi.
        context.user_data["songs"] = songs

        keyboard = []
        for index in range(0, len(songs), 2):
            row = [
                InlineKeyboardButton(
                    f"🎵 {index + 1}. {songs[index]['title'][:35]}",
                    callback_data=f"song:{index}",
                )
            ]

            if index + 1 < len(songs):
                row.append(
                    InlineKeyboardButton(
                        f"🎵 {index + 2}. {songs[index + 1]['title'][:35]}",
                        callback_data=f"song:{index + 1}",
                    )
                )

            keyboard.append(row)

        await status.edit_text(
            f"🎶 “{query}” uchun {len(songs)} ta natija:\n"
            "Kerakli qo‘shiqni tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception:
        logger.exception("Qo‘shiq qidirishda xato")
        await status.edit_text(
            "❌ Qidiruv amalga oshmadi. Birozdan keyin qayta urinib ko‘ring."
        )


async def select_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    match = re.fullmatch(r"song:(\d+)", query.data or "")
    if not match:
        return

    index = int(match.group(1))
    songs = context.user_data.get("songs", [])

    if index < 0 or index >= len(songs):
        await query.message.reply_text(
            "Natijalar eskirgan. Qo‘shiq nomini qaytadan yuboring."
        )
        return

    song = songs[index]
    status = await query.message.reply_text(
        f"⏳ Yuklanmoqda:\n{song['title']}\n\n"
        "Bu biroz vaqt olishi mumkin."
    )

    try:
        with tempfile.TemporaryDirectory(prefix="music_") as folder:
            audio_path = await asyncio.to_thread(
                download_audio_sync,
                song["url"],
                folder,
            )

            with open(audio_path, "rb") as audio_file:
                await query.message.reply_audio(
                    audio=audio_file,
                    title=song["title"][:64],
                    filename="music.mp3",
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                    pool_timeout=30,
                )

        await status.delete()

    except Exception as exc:
        logger.exception("Audio yuklashda xato: %s", song["url"])

        error_text = str(exc).lower()
        if "ffmpeg" in error_text or "ffprobe" in error_text:
            reason = "Serverda FFmpeg topilmadi."
        elif "sign in to confirm" in error_text or "bot" in error_text:
            reason = "YouTube bu so‘rovni blokladi."
        elif "private video" in error_text or "unavailable" in error_text:
            reason = "Bu qo‘shiq manbada mavjud emas."
        else:
            reason = "Manbadan audioni olib bo‘lmadi."

        try:
            await status.edit_text(
                f"❌ {reason}\n\n"
                "Boshqa natijani tanlang yoki boshqa qo‘shiq qidiring."
            )
        except Exception:
            await query.message.reply_text(
                f"❌ {reason}\nBoshqa natijani tanlab ko‘ring."
            )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Qo‘shiq nomini yozing yoki /start buyrug‘ini yuboring."
    )


def main():
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN o‘rnatilmagan. Railway Variables bo‘limini tekshiring."
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(select_song, pattern=r"^song:\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_songs))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    logger.info("Bot ishga tushmoqda...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
