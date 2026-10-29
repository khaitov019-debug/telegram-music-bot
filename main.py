
import os
import asyncio
import logging
import tempfile
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
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Railway Variables ichida TELEGRAM_BOT_TOKEN yo'q")

MAX_RESULTS = 20


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Musiqa botiga xush kelibsiz!\n\n"
        "Qo‘shiq nomini yoki ijrochi ismini yozing.\n"
        "Masalan: Eminem Mockingbird"
    )


def search_music_sync(query):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "noplaylist": True,
        "socket_timeout": 25,
        "retries": 2,
        "extractor_retries": 2,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(
            "ytsearch20:" + query,
            download=False
        )


async def search_music(query):
    data = await asyncio.to_thread(search_music_sync, query)
    entries = (data or {}).get("entries") or []
    return [
        item for item in entries
        if item and item.get("id") and item.get("title")
    ][:MAX_RESULTS]


async def handle_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = (update.message.text or "").strip()

    if not query:
        await update.message.reply_text("Qo‘shiq nomini yozing.")
        return

    status = await update.message.reply_text("🔎 Qo‘shiq qidirilmoqda...")

    try:
        results = await search_music(query)

        if not results:
            await status.edit_text(
                "Natija topilmadi.\n"
                "Boshqa nom bilan qidirib ko‘ring."
            )
            return

        context.user_data["music_results"] = results
        keyboard = []

        for i, item in enumerate(results):
            title = item["title"]
            if len(title) > 48:
                title = title[:45] + "..."

            keyboard.append([
                InlineKeyboardButton(
                    f"{i + 1}. {title}",
                    callback_data=f"song:{i}"
                )
            ])

        await status.edit_text(
            f"🎶 {len(results)} ta natija topildi.\n"
            "Kerakli qo‘shiqni tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception:
        log.exception("YouTube qidiruv xatosi")
        await status.edit_text(
            "❌ Qidiruvda xato yuz berdi.\n"
            "Railway Deploy Logs orqali xatoni tekshirish kerak."
        )


def download_audio_sync(url, folder):
    output = os.path.join(folder, "audio.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 2,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    for name in os.listdir(folder):
        if name.endswith(".mp3"):
            return os.path.join(folder, name)

    raise FileNotFoundError("Audio fayl topilmadi")


async def select_song(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    try:
        index = int(query.data.split(":")[1])
        results = context.user_data.get("music_results", [])

        if index < 0 or index >= len(results):
            await query.message.reply_text(
                "Natijalar eskirgan. Qo‘shiqni qaytadan qidiring."
            )
            return

        item = results[index]
        video_id = item["id"]
        url = item.get("url")

        if not url or not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={video_id}"

        await query.message.reply_text(
            f"⬇️ Yuklanmoqda: {item['title']}"
        )

        with tempfile.TemporaryDirectory() as folder:
            path = await asyncio.to_thread(
                download_audio_sync, url, folder
            )

            with open(path, "rb") as audio:
                await query.message.reply_audio(
                    audio=audio,
                    title=item["title"][:64],
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                )

    except Exception:
        log.exception("Audio yuklash yoki yuborish xatosi")
        await query.message.reply_text(
            "❌ Audio yuklanmadi. Railway Deploy Logs'dagi "
            "xatoni tekshirish kerak."
        )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "Qo‘shiq nomini yozing — natijadan birini tanlang.\n"
        "Bot tanlangan audio faylni yuborishga harakat qiladi."
    )


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(select_song, pattern=r"^song:\d+$"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search)
    )

    log.info("Musiqa bot ishga tushmoqda...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
