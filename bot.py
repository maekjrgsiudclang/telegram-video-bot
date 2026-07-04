import os
import time
import uuid
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
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
from config import BOT_TOKEN, TEMP_DIR, QUALITY_PRESETS
from downloader import get_file_size, download_file, get_filename_from_url
from sender import prepare_video
from database import init_db, upsert_user, is_banned, log_download
from admin import admin_command, admin_callback
from download_queue import queue

url_store = {}
cancel_flags = {}
bot_app = None


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        "Send me a direct download link to a video and I'll download it for you.\n\n"
        "You can send multiple links — they'll be queued and downloaded one by one.\n\n"
        "Commands:\n"
        "/queue — Check queue status\n"
        "/clear — Clear your queue\n"
        "/cancel_all — Cancel all pending downloads"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        "How to use:\n\n"
        "1. Send one or more direct video URLs\n"
        "2. Pick a quality for each (or use /default to set a default)\n"
        "3. Bot downloads them one by one in queue\n\n"
        "Commands:\n"
        "/queue — See your queue\n"
        "/clear — Clear your queue\n"
        "/cancel_all — Cancel all pending"
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username, user.first_name)

    if is_banned(user.id):
        await update.message.reply_text("You are banned from using this bot.")
        return

    text = update.message.text.strip()
    urls = [line.strip() for line in text.splitlines() if line.strip().startswith(("http://", "https://"))]

    if not urls:
        await update.message.reply_text("Please send a valid URL starting with http:// or https://")
        return

    if len(urls) == 1:
        url = urls[0]
        status_msg = await update.message.reply_text("Checking file size...")
        try:
            file_size = await get_file_size(url)
        except Exception as e:
            await status_msg.edit_text(f"Error checking file: {e}")
            return

        if file_size is None:
            await status_msg.edit_text("Could not fetch file info. Make sure the link is a direct download URL.")
            return

        size_mb = file_size / (1024 * 1024)
        filename = get_filename_from_url(url)

        url_id = str(uuid.uuid4())[:8]
        url_store[url_id] = url

        keyboard = []
        for label in QUALITY_PRESETS:
            keyboard.append([InlineKeyboardButton(label, callback_data=f"{label}|{url_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await status_msg.edit_text(
            f"File: `{filename}`\nSize: {size_mb:.1f} MB\n\nChoose quality:",
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
    else:
        for url in urls:
            queue.add(user.id, url, "best")

        status_msg = await update.message.reply_text(
            f"Added {len(urls)} links to queue.\n"
            f"Total in queue: {queue.get_status(user.id)['total']}\n\n"
            "Processing with best quality. Use /default to change."
        )

        if not queue.queues[user.id].processing:
            asyncio.create_task(process_queue(user.id, status_msg))


async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    quality, url_id = data.split("|", 1)
    url = url_store.pop(url_id, None)

    if not url:
        await query.edit_message_text("Session expired. Send the URL again.")
        return

    filename = get_filename_from_url(url)
    user_id = query.from_user.id

    os.makedirs(TEMP_DIR, exist_ok=True)
    download_path = os.path.join(TEMP_DIR, filename)

    dl_id = str(uuid.uuid4())[:8]
    cancel_flags[dl_id] = False

    cancel_btn = [[InlineKeyboardButton("Cancel", callback_data=f"cancel|{dl_id}")]]
    progress_msg = await query.edit_message_text(
        "Downloading... 0%", reply_markup=InlineKeyboardMarkup(cancel_btn)
    )
    last_update = [0.0]

    async def on_progress(downloaded: int, total: int):
        now = time.time()
        if now - last_update[0] < 3:
            return
        last_update[0] = now
        pct = (downloaded / total) * 100
        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
        try:
            await progress_msg.edit_text(
                f"Downloading... {bar} {pct:.0f}%",
                reply_markup=InlineKeyboardMarkup(cancel_btn),
            )
        except Exception:
            pass

    def is_cancelled():
        return cancel_flags.get(dl_id, False)

    try:
        await download_file(url, download_path, on_progress, is_cancelled)
    except Exception as e:
        cancel_flags.pop(dl_id, None)
        if "Cancelled" in str(e):
            if os.path.exists(download_path):
                os.remove(download_path)
            await progress_msg.edit_text("Download cancelled.")
        else:
            await progress_msg.edit_text(f"Download failed: {e}")
        return

    cancel_flags.pop(dl_id, None)

    await progress_msg.edit_text("Processing video...")

    async def on_process(step: str):
        if step == "compressing":
            await progress_msg.edit_text("Compressing video...")
        elif step == "splitting":
            await progress_msg.edit_text("Splitting large file...")

    try:
        parts = await prepare_video(download_path, quality, on_process)
    except Exception as e:
        await progress_msg.edit_text(f"Processing failed: {e}")
        if os.path.exists(download_path):
            os.remove(download_path)
        return

    file_size_actual = os.path.getsize(parts[0]) if parts else 0
    log_download(user_id, filename, url, quality, file_size_actual)

    if len(parts) == 1:
        await progress_msg.edit_text("Uploading video...")
        with open(parts[0], "rb") as f:
            await query.message.reply_video(video=f, filename=filename, caption=filename)
        await progress_msg.delete()
    else:
        total_parts = len(parts)
        await progress_msg.edit_text(f"Uploading {total_parts} parts...")
        for i, part_path in enumerate(parts, 1):
            part_name = f"{Path(filename).stem} (Part {i}/{total_parts}){Path(filename).suffix}"
            caption = f"Part {i}/{total_parts}"
            with open(part_path, "rb") as f:
                await query.message.reply_video(
                    video=f, filename=part_name, caption=caption
                )
        await progress_msg.delete()

    for p in parts:
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(download_path):
        os.remove(download_path)


async def process_queue(user_id: int, status_msg=None):
    while True:
        item = queue.get_pending(user_id)
        if not item:
            queue.remove_done(user_id)
            if status_msg:
                try:
                    await status_msg.edit_text("Queue complete!")
                except Exception:
                    pass
            break

        queue.mark_processing(user_id, item.url)
        filename = get_filename_from_url(item.url)

        os.makedirs(TEMP_DIR, exist_ok=True)
        download_path = os.path.join(TEMP_DIR, filename)

        dl_id = str(uuid.uuid4())[:8]
        cancel_flags[dl_id] = False

        cancel_btn = [[InlineKeyboardButton("Cancel", callback_data=f"cancel|{dl_id}")]]
        status = queue.get_status(user_id)
        progress_msg = await bot_app.bot.send_message(
            user_id,
            f"Queue: {status['done'] + 1}/{status['total']}\nDownloading {filename}...",
            reply_markup=InlineKeyboardMarkup(cancel_btn),
        )
        last_update = [0.0]

        async def on_progress(downloaded: int, total: int):
            now = time.time()
            if now - last_update[0] < 5:
                return
            last_update[0] = now
            pct = (downloaded / total) * 100
            bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
            try:
                await progress_msg.edit_text(
                    f"Queue: {status['done'] + 1}/{status['total']}\n"
                    f"Downloading {filename}... {bar} {pct:.0f}%",
                    reply_markup=InlineKeyboardMarkup(cancel_btn),
                )
            except Exception:
                pass

        def is_cancelled():
            return cancel_flags.get(dl_id, False)

        try:
            await download_file(item.url, download_path, on_progress, is_cancelled)
        except Exception as e:
            cancel_flags.pop(dl_id, None)
            queue.mark_failed(user_id, item.url)
            if "Cancelled" in str(e):
                if os.path.exists(download_path):
                    os.remove(download_path)
                try:
                    await progress_msg.edit_text(f"Cancelled: {filename}")
                except Exception:
                    pass
            else:
                try:
                    await progress_msg.edit_text(f"Failed: {filename} — {e}")
                except Exception:
                    pass
            continue

        cancel_flags.pop(dl_id, None)

        try:
            await progress_msg.edit_text(f"Queue: {status['done'] + 1}/{status['total']}\nProcessing {filename}...")
        except Exception:
            pass

        async def on_process(step: str):
            pass

        try:
            parts = await prepare_video(download_path, item.quality, on_process)
        except Exception as e:
            queue.mark_failed(user_id, item.url)
            try:
                await progress_msg.edit_text(f"Processing failed: {filename} — {e}")
            except Exception:
                pass
            if os.path.exists(download_path):
                os.remove(download_path)
            continue

        file_size_actual = os.path.getsize(parts[0]) if parts else 0
        log_download(user_id, filename, item.url, item.quality, file_size_actual)

        try:
            await progress_msg.edit_text(f"Queue: {status['done'] + 1}/{status['total']}\nUploading {filename}...")
        except Exception:
            pass

        try:
            if len(parts) == 1:
                with open(parts[0], "rb") as f:
                    await bot_app.bot.send_video(user_id, video=f, filename=filename, caption=filename)
            else:
                total_parts = len(parts)
                for i, part_path in enumerate(parts, 1):
                    part_name = f"{Path(filename).stem} (Part {i}/{total_parts}){Path(filename).suffix}"
                    caption = f"Part {i}/{total_parts}"
                    with open(part_path, "rb") as f:
                        await bot_app.bot.send_video(
                            user_id, video=f, filename=part_name, caption=caption
                        )
            await progress_msg.delete()
        except Exception:
            pass

        queue.mark_done(user_id, item.url)

        for p in parts:
            if os.path.exists(p):
                os.remove(p)
        if os.path.exists(download_path):
            os.remove(download_path)


async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    status = queue.get_status(user.id)

    if status["total"] == 0:
        await update.message.reply_text("Your queue is empty.")
        return

    lines = [f"Queue: {status['pending']} pending, {status['processing']} processing, {status['done']} done, {status['failed']} failed\n"]
    for i, item in enumerate(status["items"], 1):
        name = get_filename_from_url(item.url)
        lines.append(f"{i}. {name} [{item.status}]")

    keyboard = [[InlineKeyboardButton("Clear Queue", callback_data="clear_queue")]]
    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard))


async def clear_queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    queue.clear(user.id)
    await update.message.reply_text("Queue cleared.")


async def cancel_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    queue.clear(query.from_user.id)
    await query.edit_message_text("All downloads cancelled and queue cleared.")


async def clear_queue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    queue.clear(query.from_user.id)
    await query.edit_message_text("Queue cleared.")


def start_health_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


def main():
    global bot_app

    if not BOT_TOKEN:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN environment variable")

    init_db()
    threading.Thread(target=start_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    bot_app = app

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("clear", clear_queue_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(cancel_callback, pattern=r"^cancel\|"))
    app.add_handler(CallbackQueryHandler(clear_queue_callback, pattern=r"^clear_queue$"))
    app.add_handler(CallbackQueryHandler(cancel_all_callback, pattern=r"^cancel_all$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin\|"))
    app.add_handler(CallbackQueryHandler(quality_callback))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
