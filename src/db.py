"""
SQLite persistence layer for MeshtasticBot.

Provides init_db() to open/create the database and store_message() to persist
received channel messages with deduplication by packet ID.
"""

import os
import sqlite3
import logging

log = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    packet_id   TEXT    NOT NULL UNIQUE,
    channel     INTEGER NOT NULL,
    sender_id   TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    received_at TEXT    NOT NULL
);
"""


def init_db(path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite database at *path* and return the connection."""
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()
    log.info(f"Message log database opened: {path}")
    return conn


def get_recent_messages(
    conn: sqlite3.Connection,
    channel: int,
    hours: int = 24,
) -> list[dict]:
    """Return messages from *channel* received within the last *hours* hours, oldest first."""
    try:
        cur = conn.execute(
            "SELECT sender_id, text, received_at FROM messages "
            "WHERE channel = ? AND received_at >= datetime('now', ? || ' hours') "
            "ORDER BY received_at ASC",
            (channel, f"-{hours}"),
        )
        return [{"sender_id": r[0], "text": r[1], "received_at": r[2]} for r in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error(f"Failed to query messages: {exc}")
        return []


def get_last_messages(
    conn: sqlite3.Connection,
    channel: int,
    limit: int = 10,
) -> list[dict]:
    """Return the *limit* most recent messages from *channel*, in chronological order."""
    try:
        cur = conn.execute(
            "SELECT sender_id, text, received_at FROM ("
            "  SELECT sender_id, text, received_at FROM messages "
            "  WHERE channel = ? ORDER BY received_at DESC LIMIT ?"
            ") ORDER BY received_at ASC",
            (channel, limit),
        )
        return [{"sender_id": r[0], "text": r[1], "received_at": r[2]} for r in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error(f"Failed to query last messages: {exc}")
        return []


def get_messages_page(
    conn: sqlite3.Connection,
    channel: int | None,
    date_from: str | None,
    date_to: str | None,
    page: int,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """Return a page of messages with optional channel/date filters, and the total count."""
    conditions = []
    params: list = []

    if channel is not None:
        conditions.append("channel = ?")
        params.append(channel)
    if date_from:
        conditions.append("received_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("received_at <= ?")
        params.append(date_to + "T23:59:59")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM messages {where}", params).fetchone()[0]
        offset = (page - 1) * page_size
        cur = conn.execute(
            f"SELECT channel, sender_id, text, received_at FROM messages {where} "
            f"ORDER BY received_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        rows = [
            {"channel": r[0], "sender_id": r[1], "text": r[2], "received_at": r[3]}
            for r in cur.fetchall()
        ]
        return rows, total
    except sqlite3.Error as exc:
        log.error(f"Failed to query messages page: {exc}")
        return [], 0


def get_message_counts(conn: sqlite3.Connection) -> dict:
    """Return total message count and count for the last 24 hours."""
    try:
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE received_at >= datetime('now', '-24 hours')"
        ).fetchone()[0]
        channels = conn.execute(
            "SELECT channel, COUNT(*) FROM messages GROUP BY channel ORDER BY channel"
        ).fetchall()
        return {"total": total, "last_24h": today, "by_channel": dict(channels)}
    except sqlite3.Error as exc:
        log.error(f"Failed to get message counts: {exc}")
        return {"total": 0, "last_24h": 0, "by_channel": {}}


def purge_old_messages(conn: sqlite3.Connection, days: int = 365) -> int:
    """Delete messages older than *days* days. Returns the number of rows deleted."""
    try:
        cur = conn.execute(
            "DELETE FROM messages WHERE received_at < datetime('now', ? || ' days')",
            (f"-{days}",),
        )
        conn.commit()
        if cur.rowcount:
            log.info(f"Purged {cur.rowcount} message(s) older than {days} days.")
        return cur.rowcount
    except sqlite3.Error as exc:
        log.error(f"Failed to purge old messages: {exc}")
        return 0

def store_message(
    conn: sqlite3.Connection,
    packet_id: str,
    channel: int,
    sender_id: str,
    text: str,
    received_at: str,
) -> None:
    """Insert a message, silently ignoring duplicates (same packet_id)."""
    try:
        conn.execute(
            "INSERT OR IGNORE INTO messages (packet_id, channel, sender_id, text, received_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (packet_id, channel, sender_id, text, received_at),
        )
        conn.commit()
    except sqlite3.Error as exc:
        log.error(f"Failed to store message (packet_id={packet_id}): {exc}")
