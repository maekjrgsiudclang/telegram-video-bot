import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_ID, TEMP_DIR
from database import (
    get_stats, get_users, get_total_users,
    get_downloads, get_total_downloads, get_download_by_id,
    ban_user, unban_user,
)
from downloader import download_file


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    keyboard = [
        [
            InlineKeyboardButton("Stats", callback_data="admin|stats"),
            InlineKeyboardButton("Users", callback_data="admin|users|0"),
            InlineKeyboardButton("History", callback_data="admin|history|0"),
        ]
    ]
    await update.message.reply_text(
        "Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return

    await query.answer()
    data = query.data
    parts = data.split("|")
    action = parts[1]

    if action == "back":
        keyboard = [
            [
                InlineKeyboardButton("Stats", callback_data="admin|stats"),
                InlineKeyboardButton("Users", callback_data="admin|users|0"),
                InlineKeyboardButton("History", callback_data="admin|history|0"),
            ]
        ]
        await query.edit_message_text("Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))
    elif action == "stats":
        await show_stats(query)
    elif action == "users":
        page = int(parts[2]) if len(parts) > 2 else 0
        await show_users(query, page)
    elif action == "unban":
        user_id = int(parts[2])
        unban_user(user_id)
        await query.edit_message_text(f"User {user_id} unbanned.")
    elif action == "ban":
        user_id = int(parts[2])
        ban_user(user_id)
        await query.edit_message_text(f"User {user_id} banned.")
    elif action == "history":
        page = int(parts[2]) if len(parts) > 2 else 0
        await show_history(query, page)
    elif action == "forward":
        download_id = int(parts[2])
        await forward_video(query, download_id)


async def show_stats(query):
    stats = get_stats()
    text = (
        f"Stats\n\n"
        f"Total users: {stats['total_users']}\n"
        f"Active (24h): {stats['active_24h']}\n"
        f"Total downloads: {stats['total_downloads']}\n"
        f"Banned users: {stats['banned_users']}"
    )
    keyboard = [[InlineKeyboardButton("Back", callback_data="admin|back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_users(query, page: int):
    per_page = 5
    users = get_users(page, per_page)
    total = get_total_users()
    total_pages = max(1, (total + per_page - 1) // per_page)

    if not users:
        await query.edit_message_text("No users found.")
        return

    lines = []
    keyboard = []
    for u in users:
        name = u["username"] or u["first_name"] or str(u["user_id"])
        status = "BANNED" if u["is_banned"] else "active"
        lines.append(f"@{name} ({status})")

        if u["is_banned"]:
            keyboard.append([InlineKeyboardButton(
                f"Unban @{name}", callback_data=f"admin|unban|{u['user_id']}"
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                f"Ban @{name}", callback_data=f"admin|ban|{u['user_id']}"
            )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("< Prev", callback_data=f"admin|users|{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next >", callback_data=f"admin|users|{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("Back", callback_data="admin|back")])

    text = f"Users (page {page + 1}/{total_pages}):\n\n" + "\n".join(lines)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_history(query, page: int):
    per_page = 5
    downloads = get_downloads(page, per_page)
    total = get_total_downloads()
    total_pages = max(1, (total + per_page - 1) // per_page)

    if not downloads:
        await query.edit_message_text("No downloads found.")
        return

    lines = []
    keyboard = []
    for d in downloads:
        name = d["username"] or d["first_name"] or "unknown"
        size_mb = d["file_size"] / (1024 * 1024) if d["file_size"] else 0
        lines.append(f"{d['filename']} - @{name} - {size_mb:.1f}MB")
        keyboard.append([InlineKeyboardButton(
            f"Forward {d['filename']}", callback_data=f"admin|forward|{d['id']}"
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("< Prev", callback_data=f"admin|history|{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next >", callback_data=f"admin|history|{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("Back", callback_data="admin|back")])

    text = f"Downloads (page {page + 1}/{total_pages}):\n\n" + "\n".join(lines)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def forward_video(query, download_id: int):
    dl = get_download_by_id(download_id)
    if not dl:
        await query.edit_message_text("Download not found.")
        return

    await query.edit_message_text("Downloading video to forward...")

    filename = dl["filename"]
    url = dl["url"]

    os.makedirs(TEMP_DIR, exist_ok=True)
    download_path = os.path.join(TEMP_DIR, f"admin_{filename}")

    try:
        await download_file(url, download_path)
    except Exception as e:
        await query.edit_message_text(f"Failed to download: {e}")
        return

    await query.edit_message_text("Sending video...")

    try:
        with open(download_path, "rb") as f:
            await query.message.reply_video(video=f, filename=filename, caption=filename)
        await query.delete_message()
    except Exception as e:
        await query.edit_message_text(f"Failed to send: {e}")
    finally:
        if os.path.exists(download_path):
            os.remove(download_path)
