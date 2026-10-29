
import os
import re
import asyncio
import logging
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MAX_RESULTS = 20

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("musicbot")


def get_json(url, params=None):
    response = requests.get(
        url, params=params, timeout=15,
        headers={"User-Agent": "MusicSearchBot/1.0"}
    )
    response.raise_for_status()
    return response.json()


def search_itunes(query):
    data = get_json(
        "https://itunes.apple.com/search",
        {"term": query, "entity": "song", "limit": 10}
    )
    results = []

    for item in data.get("results", []):
        results.append({
            "title": f"{item.get('trackName', 'Unknown')} — "
                     f"{item.get('artistName', 'Unknown')}",
            "url": item.get("trackViewUrl", ""),
            "audio_url": item.get("previewUrl"),
            "source": "iTunes",
        })

    return results


def search_audius(query):
    data = get_json(
        "https://api.audius.co/v1/tracks/search",
        {"query": query, "limit": 10}
    )
    results = []

    for item in data.get("data", []):
        track_id = item.get("id")
        if not track_id:
            continue

        results.append({
            "title": f"{item.get('title', 'Unknown')} — "
                     f"{(item.get('user') or {}).get('name', 'Audius')}",
            "url": f"https://audius.co/tracks/{track_id}",
            "audio_url": None,
            "source": "Audius",
        })

    return results


def search_soundcloud(query):
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        data = ydl.extract_info(
            f"scsearch10:{query}", download=False
        )

    results = []
    for item in (data or {}).get("entries", []):
        if not item:
            continue

        url = item.get("webpage_url") or item.get("url")
        if not url:
            continue
        if not str(url).startswith("http"):
            continue

        results.append({
            "title": item.get("title", "Unknown"),
            "url": url,
            "audio_url": None,
            "source": "SoundCloud",
        })

    return results


def search_all(query):
    results = []

    # Har bir katalogni mustaqil sinash: bittasi ishlamasa,
    # qolgan kataloglar ham tekshiriladi.
    for search_function in (search_itunes, search_audius, search_soundcloud):
        try:
            results.extend(search_function(query))
        except Exception:
            log.exception("Qidiruv manbasi ishlamadi: %s", search_function.__name__)

    unique = []
    seen = set()

    for item in results:
        key = item.get("url")
        if key and key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:MAX_RESULTS]


def download_audio(item, folder):
    direct_url = item.get("audio_url")

    if direct_url:
        response = requests.get(direct_url, timeout=30, stream=True)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        extension = ".m4a" if "mp4" in content_type else ".mp3"
        path = Path(folder) / ("track" + extension)

        with open(path, "wb") as file:
            for chunk in response.iter_content(1024 * 256):
                if chunk:
                    file.write(chunk)

        if path.stat().st_size:
            return str(path)

    # Preview mavjud bo'lmasa, ruxsat etilgan manbadan
    # yt-dlp orqali audio olishga urinadi.
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(folder) / "track.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 25,
        "retries": 2,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([item["url"]])

    for path in Path(folder).iterdir():
        if path.is_file() and path.suffix.lower() not in (
            ".part", ".ytdl", ".json"
        ):
            return str(path)

    raise FileNotFoundError("Audio fayl topilmadi")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Qo‘shiq nomini yoki ijrochi ismini yozing.\n\n"
        "Qidiruv: iTunes, Audius va SoundCloud.\n"
        "Natijani tanlang — mavjud audio yuborishga harakat qilaman."
    )


async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    if not query:
        return

    if len(query) > 200:
        await update.message.reply_text("Qidiruv matnini qisqartiring.")
        return

    status = await update.message.reply_text("🔎 Bir nechta katalogdan qidiryapman...")

    try:
        results = await asyncio.to_thread(search_all, query)

        if not results:
            await status.edit_text(
                "😕 Natija topilmadi. Boshqa nom bilan urinib ko‘ring."
            )
            return

        context.user_data["songs"] = results
        keyboard = []

        for i in range(0, len(results), 2):
            row = []
            for j in range(i, min(i + 2, len(results))):
                item = results[j]
                row.append(
                    InlineKeyboardButton(
                        f"{j + 1}. {item['title'][:28]}",
                        callback_data=f"song:{j}"
                    )
                )
            keyboard.append(row)

        await status.edit_text(
            f"🎶 {len(results)} ta natija topildi.\nTanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception:
        log.exception("Qidiruv xatosi")
        await status.edit_text("Qidiruvda xato. Railway loglarini tekshiring.")


async def select_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    match = re.fullmatch(r"song:(\d+)", query.data or "")
    if not match:
        return

    index = int(match.group(1))
    songs = context.user_data.get("songs", [])

    if index >= len(songs):
        await query.message.reply_text("Qaytadan qidiruv qiling.")
        return

    item = songs[index]
    status = await query.message.reply_text(
        f"⏳ {item['title']}\nManba: {item['source']}"
    )

    try:
        with tempfile.TemporaryDirectory(prefix="music_") as folder:
            path = await asyncio.to_thread(download_audio, item, folder)

            if Path(path).stat().st_size > 49 * 1024 * 1024:
                await status.edit_text(
                    "Fayl juda katta. Bu manbadan Telegramga yuborib bo‘lmadi."
                )
                return

            with open(path, "rb") as audio:
                await query.message.reply_audio(
                    audio=audio,
                    title=item["title"][:64],
                    filename=Path(path).name,
                    read_timeout=120,
                    write_timeout=120,
                )

        await status.delete()

    except Exception:
        log.exception("Audio yuborish xatosi: %s", item.get("url"))
        await status.edit_text(
            "❌ Bu natijadan audio olishning iloji bo‘lmadi.\n"
            "Boshqa natijani tanlab ko‘ring. Ayrim kataloglarda faqat "
            "30 soniyalik namuna bo‘lishi mumkin."
        )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Qo‘shiq nomini yozing yoki /start yuboring.")


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN Railway Variables ichida yo‘q.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(select_song, pattern=r"^song:\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    log.info("Bot ishga tushdi")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
