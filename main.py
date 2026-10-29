
import os
import asyncio
import logging
import tempfile
from pathlib import Path

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("music_bot")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MAX_RESULTS = 20

if not TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN Railway Variables ichida mavjud emas!"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 MUSIQA BOTI\n\n"
        "Qo‘shiq nomi yoki ijrochisini yozing.\n"
        "Masalan: Eminem Mockingbird\n\n"
        "Natijalar yonma-yon chiqadi. Keraklisini tanlang."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Qo‘shiq nomini yozing va ro‘yxatdan tanlang.\n"
        "Video havolasi yuborilsa, bot uni audio sifatida "
        "yuklab olishga ham urinadi."
    )


def search_music_sync(song_name):
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 2,
        "extractor_retries": 2,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        data = ydl.extract_info(
            "ytsearch20:" + song_name,
            download=False,
        )

    results = []
    seen = set()

    for item in (data or {}).get("entries") or []:
        if not item:
            continue

        title = item.get("title")
        video_id = item.get("id")

        if not title or not video_id:
            continue

        # YouTube uchun haqiqiy video havolasini yasash
        url = "https://www.youtube.com/watch?v=" + video_id

        if url in seen:
            continue

        seen.add(url)
        results.append({
            "title": title,
            "url": url,
        })

        if len(results) >= MAX_RESULTS:
            break

    return results


async def search_music(song_name):
    return await asyncio.to_thread(search_music_sync, song_name)


def download_audio_sync(url, folder):
    output = str(Path(folder) / "track.%(ext)s")

    options = {
        "format": "bestaudio/best",
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 35,
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

    for file in Path(folder).iterdir():
