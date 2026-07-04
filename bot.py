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
from config import BOT_TOKEN, TEMP_DIR
from downloader import get_file_size, download_file, get_filename_from_url
from sender import prepare_video
from database import init_db, upsert_user, is_banned, log_download
from admin import admin_command, admin_callback
from download_queue import queue

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
        "Send me a direct video link and I'll download it for you.\n\n"
        "You can send multiple links — they'll be queued and downloaded one by one.\n\n"
        "Use /help for full instructions."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        "Video Downloader Bot\n\n"
        "How to use:\n"
        "1. Send a direct video URL (e.g., from webtor.io)\n"
        "2. Bot downloads it in original quality and sends it to you\n"
        "3. You can send multiple URLs — they'll be queued\n\n"
        "Splitting:\n"
        "Files over 45MB are split into parts automatically.\n"
        "Each part is labeled (e.g., Part 1/3).\n\n"
        "Commands:\n"
        "/start — Welcome message\n"
        "/help — This message\n"
        "/queue — Check your download queue\n"
        "/clear — Clear your queue\n"
        "/admin — Admin panel (admin only)"
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

    for url in urls:
        queue.add(user.id, url)

    count = len(urls)
    status = queue.get_status(user.id)
    await update.message.reply_text(
        f"Added {count} link{'s' if count > 1 else ''} to queue.\n"
        f"Total in queue: {status['total']}"
    )

    if not queue.queues[user.id].processing:
        asyncio.create_task(process_queue(user.id))


async def process_queue(user_id: int):
    while True:
        item = queue.get_pending(user_id)
        if not item:
            queue.remove_done(user_id)
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
            f"Queue {status['done'] + 1}/{status['total']}\nDownloading {filename}...",
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
                    f"Queue {status['done'] + 1}/{status['total']}\n"
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
                await bot_app.bot.send_message(user_id, f"Cancelled: {filename}")
            else:
                await bot_app.bot.send_message(user_id, f"Failed: {filename}\n{e}")
            try:
                await progress_msg.delete()
            except Exception:
                pass
            continue

        cancel_flags.pop(dl_id, None)

        await bot_app.bot.send_message(user_id, f"Downloaded {filename}\nProcessing...")
        try:
            await progress_msg.delete()
        except Exception:
            pass

        try:
            parts = prepare_video(download_path)
        except Exception as e:
            queue.mark_failed(user_id, item.url)
            await bot_app.bot.send_message(user_id, f"Processing failed: {filename}\n{e}")
            if os.path.exists(download_path):
                os.remove(download_path)
            continue

        file_size_actual = os.path.getsize(parts[0]) if parts else 0

        if len(parts) == 1:
            await bot_app.bot.send_message(user_id, f"Uploading {filename}...")
            try:
                with open(parts[0], "rb") as f:
                    sent_msg = await bot_app.bot.send_video(
                        user_id, video=f, filename=filename, caption=filename,
                        read_timeout=600, write_timeout=600, connect_timeout=60
                    )
                log_download(user_id, filename, item.url, "original", file_size_actual, sent_msg.chat.id, sent_msg.message_id)
            except Exception as e:
                await bot_app.bot.send_message(user_id, f"Failed to send {filename}: {e}")
        else:
            total_parts = len(parts)
            await bot_app.bot.send_message(user_id, f"Uploading {filename} ({total_parts} parts)...")
            for i, part_path in enumerate(parts, 1):
                part_name = f"{Path(filename).stem} (Part {i}/{total_parts}){Path(filename).suffix}"
                caption = f"Part {i}/{total_parts}"
                try:
                    with open(part_path, "rb") as f:
                        sent_msg = await bot_app.bot.send_video(
                            user_id, video=f, filename=part_name, caption=caption,
                            read_timeout=600, write_timeout=600, connect_timeout=60
                        )
                    log_download(user_id, part_name, item.url, "original", os.path.getsize(part_path), sent_msg.chat.id, sent_msg.message_id)
                except Exception as e:
                    await bot_app.bot.send_message(user_id, f"Failed to send {part_name}: {e}")

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


async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    _, dl_id = data.split("|", 1)

    if dl_id in cancel_flags:
        cancel_flags[dl_id] = True
        await query.edit_message_text("Cancelling...")


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

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
