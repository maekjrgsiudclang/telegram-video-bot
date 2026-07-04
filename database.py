import sqlite3
import os
from typing import Optional, List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_banned INTEGER DEFAULT 0,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT,
            url TEXT,
            quality TEXT,
            file_size INTEGER,
            chat_id INTEGER,
            message_id INTEGER,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
    """)
    conn.close()


def upsert_user(user_id: int, username: str = None, first_name: str = None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO users (user_id, username, first_name, last_active)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            username = COALESCE(excluded.username, users.username),
            first_name = COALESCE(excluded.first_name, users.first_name),
            last_active = CURRENT_TIMESTAMP
    """, (user_id, username, first_name))
    conn.commit()
    conn.close()


def is_banned(user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row is not None and row["is_banned"] == 1


def ban_user(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def unban_user(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def log_download(user_id: int, filename: str, url: str, quality: str, file_size: int, chat_id: int = None, message_id: int = None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO downloads (user_id, filename, url, quality, file_size, chat_id, message_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, filename, url, quality, file_size, chat_id, message_id),
    )
    conn.commit()
    conn.close()


def get_stats() -> Dict[str, Any]:
    conn = get_conn()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active_24h = conn.execute(
        "SELECT COUNT(*) FROM users WHERE last_active > datetime('now', '-1 day')"
    ).fetchone()[0]
    total_downloads = conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
    banned_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1").fetchone()[0]
    conn.close()
    return {
        "total_users": total_users,
        "active_24h": active_24h,
        "total_downloads": total_downloads,
        "banned_users": banned_users,
    }


def get_users(page: int = 0, per_page: int = 5) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, username, first_name, is_banned FROM users ORDER BY first_seen DESC LIMIT ? OFFSET ?",
        (per_page, page * per_page),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_total_users() -> int:
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count


def get_downloads(page: int = 0, per_page: int = 5) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT d.id, d.filename, d.url, d.quality, d.file_size, d.downloaded_at,
                  u.username, u.first_name
           FROM downloads d
           LEFT JOIN users u ON d.user_id = u.user_id
           ORDER BY d.downloaded_at DESC LIMIT ? OFFSET ?""",
        (per_page, page * per_page),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_total_downloads() -> int:
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
    conn.close()
    return count


def get_download_by_id(download_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute(
        """SELECT d.id, d.filename, d.url, d.quality, d.file_size, d.chat_id, d.message_id,
                  u.username, u.first_name
           FROM downloads d
           LEFT JOIN users u ON d.user_id = u.user_id
           WHERE d.id = ?""",
        (download_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
