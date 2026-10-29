
import os
import asyncio
import logging
import tempfile
from pathlib import Path

import yt_dlp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN Railway Variables'da yo'q")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("music_bot")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Musiqa botiga xush kelibsiz!\n"
        "Qo‘shiq nomini yuboring — bot eng mos natijani "
        "topib, audio yuborishga urinadi."
    )


def search_candidates_sync(song_name):
    """YouTube va SoundCloud'dan nom bo'yicha natijalarni qidiradi."""
    candidates = []
    sources = [
        "ytsearch5:" + song_name,
        "scsearch5:" + song_name,
    ]

    for search_term in sources:
        try:
            opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "extract_flat": True,
                "noplaylist": True,
                "socket_timeout": 20,
                "retries": 1,
            }

            with yt_dlp.YoutubeDL(opts) as ydl:
                data = ydl.extract_info(search_term, download=False)

            for item in (data or {}).get("entries") or []:
                if not item or not item.get("title"):
                    continue

                url = item.get("webpage_url") or item.get("url")

                if not url:
                    item_id = item.get("id")
                    if item_id and "youtube" in search_term:
                        url = "https://www.youtube.com/watch?v=" + item_id

                if url:
                    candidates.append({
                        "title": item["title"],
                        "url": url,
                        "source": search_term.split(":")[0],
                    })

        except Exception:
            log.exception("Qidiruv manbasi ishlamadi: %s", search_term)

    # Dublikat natijalarni olib tashlash
    unique = []
    seen = set()

    for item in candidates:
        key = item["url"]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def download_audio_sync(url, folder):
    """Ruxsatli manbadagi audioni MP3 formatida yuklaydi."""
    output = os.path.join(folder, "track.%(ext)s")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 2,
        "extractor_retries": 1,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    files = list(Path(folder).glob("track*.mp3"))
    if not files:
        raise FileNotFoundError("Yuklangan MP3 fayl topilmadi")

    return str(files[0])


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    song_name = (message.text or "").strip()

    if not song_name:
        return

    status = await message.reply_text(
        "🔎 Qo‘shiq qidirilmoqda..."
    )

    try:
        candidates = await asyncio.to_thread(
            search_candidates_sync, song_name
        )

        if not candidates:
            await status.edit_text(
                "❌ Qo‘shiq topilmadi. Boshqa nom bilan urinib ko‘ring."
            )
            return

        errors = []

        # Eng mos deb topilgan natijalardan boshlab sinaydi.
        for number, item in enumerate(candidates[:10], start=1):
            try:
                await status.edit_text(
                    f"⬇️ Audio olinmoqda ({number}/{min(len(candidates), 10)})\n"
                    f"🎵 {item['title'][:150]}\n"
                    f"Manba: {item['source']}"
                )

                with tempfile.TemporaryDirectory() as folder:
                    path = await asyncio.to_thread(
                        download_audio_sync, item["url"], folder
                    )

                    with open(path, "rb") as audio:
                        await message.reply_audio(
                            audio=audio,
                            title=item["title"][:64],
                            read_timeout=180,
                            write_timeout=180,
                            connect_timeout=30,
                            pool_timeout=30,
                        )

                await status.edit_text(
                    "✅ Audio yuborildi!"
                )
                return

            except Exception as exc:
                log.warning(
                    "Natija %s ishlamadi (%s): %s",
                    number, item["source"], exc,
                )
                errors.append(str(exc))

        log.error("Barcha audio urinishlari muvaffaqiyatsiz: %s", errors)
        await status.edit_text(
            "❌ To‘liq audio yuklanmadi.\n\n"
            "Sabab: manbalar yuklashga ruxsat bermadi yoki "
            "audio formati mavjud emas.\n"
            "Boshqa qo‘shiq nomi bilan urinib ko‘ring."
        )

    except Exception:
        log.exception("Musiqa qidirishda xato")
        await status.edit_text(
            "❌ Qidiruv xatosi. Railway Runtime Logs'ni tekshiring."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Qo‘shiq nomini yozing. Bot mos audio topib yuborishga urinadi."
    )


async def error_handler(update, context):
    log.error(
        "Telegram bot xatosi",
        exc_info=context.error,
    )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search)
    )
    app.add_error_handler(error_handler)

    log.info("Musiqa bot ishga tushmoqda...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
