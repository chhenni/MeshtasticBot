"""
SQLite persistence layer for MeshtasticBot.

Provides init_db() to open/create the database and store_message() to persist
received channel messages with deduplication by packet ID.
"""

import logging
import os
import sqlite3

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

CREATE_NODES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id     TEXT    PRIMARY KEY,
    long_name   TEXT,
    short_name  TEXT,
    last_seen   TEXT    NOT NULL,
    last_snr    REAL,
    last_rssi   INTEGER,
    lat         REAL,
    lon         REAL
);
"""

CREATE_COMMAND_LOG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS command_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     TEXT    NOT NULL,
    command     TEXT    NOT NULL,
    status      TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL
);
"""

CREATE_BANNED_NODES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS banned_nodes (
    node_id     TEXT    PRIMARY KEY,
    banned_at   TEXT    NOT NULL,
    reason      TEXT
);
"""


def init_db(path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite database at *path* and return the connection.

    WAL journal mode is enabled for safe concurrent access from multiple threads
    (receiver, web UI, purge loop, node sync loop). busy_timeout gives threads up
    to 5 seconds to retry before raising SQLITE_BUSY.
    """
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")  # ms — retry for up to 5 s on lock contention
    conn.execute(CREATE_TABLE_SQL)
    conn.execute(CREATE_NODES_TABLE_SQL)
    conn.execute(CREATE_COMMAND_LOG_TABLE_SQL)
    conn.execute(CREATE_BANNED_NODES_TABLE_SQL)
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


def upsert_node(
    conn: sqlite3.Connection,
    node_id: str,
    long_name: str | None = None,
    short_name: str | None = None,
    last_seen: str | None = None,
    snr: float | None = None,
    rssi: int | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> None:
    """Insert or update a node record, only overwriting non-None fields."""
    try:
        conn.execute(
            "INSERT INTO nodes (node_id, long_name, short_name, last_seen, last_snr, last_rssi, lat, lon) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET "
            "  long_name  = COALESCE(excluded.long_name,  long_name), "
            "  short_name = COALESCE(excluded.short_name, short_name), "
            "  last_seen  = COALESCE(excluded.last_seen,  last_seen), "
            "  last_snr   = COALESCE(excluded.last_snr,   last_snr), "
            "  last_rssi  = COALESCE(excluded.last_rssi,  last_rssi), "
            "  lat        = COALESCE(excluded.lat,        lat), "
            "  lon        = COALESCE(excluded.lon,        lon)",
            (node_id, long_name, short_name, last_seen, snr, rssi, lat, lon),
        )
        conn.commit()
    except sqlite3.Error as exc:
        log.error(f"Failed to upsert node (node_id={node_id}): {exc}")


def get_node(conn: sqlite3.Connection, node_id: str) -> dict | None:
    """Return a node record by exact node_id, or None if not found."""
    try:
        cur = conn.execute(
            "SELECT node_id, long_name, short_name, last_seen, last_snr, last_rssi, lat, lon "
            "FROM nodes WHERE node_id = ?",
            (node_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        keys = ("node_id", "long_name", "short_name", "last_seen", "last_snr", "last_rssi", "lat", "lon")
        return dict(zip(keys, row))
    except sqlite3.Error as exc:
        log.error(f"Failed to get node (node_id={node_id}): {exc}")
        return None


def lookup_nodes_by_name(conn: sqlite3.Connection, query: str) -> list[dict]:
    """Return nodes whose long_name or short_name contains *query* (case-insensitive)."""
    try:
        pattern = f"%{query}%"
        cur = conn.execute(
            "SELECT node_id, long_name, short_name, last_seen, last_snr, last_rssi, lat, lon "
            "FROM nodes WHERE long_name LIKE ? OR short_name LIKE ? "
            "ORDER BY last_seen DESC",
            (pattern, pattern),
        )
        keys = ("node_id", "long_name", "short_name", "last_seen", "last_snr", "last_rssi", "lat", "lon")
        return [dict(zip(keys, row)) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error(f"Failed to lookup nodes by name (query={query!r}): {exc}")
        return []


def get_all_nodes(conn: sqlite3.Connection, query: str | None = None) -> list[dict]:
    """Return all nodes sorted by last_seen descending. Optionally filter by *query*."""
    keys = ("node_id", "long_name", "short_name", "last_seen", "last_snr", "last_rssi", "lat", "lon")
    try:
        if query:
            pattern = f"%{query}%"
            cur = conn.execute(
                "SELECT node_id, long_name, short_name, last_seen, last_snr, last_rssi, lat, lon "
                "FROM nodes WHERE node_id LIKE ? OR long_name LIKE ? OR short_name LIKE ? "
                "ORDER BY last_seen DESC",
                (pattern, pattern, pattern),
            )
        else:
            cur = conn.execute(
                "SELECT node_id, long_name, short_name, last_seen, last_snr, last_rssi, lat, lon "
                "FROM nodes ORDER BY last_seen DESC"
            )
        return [dict(zip(keys, row)) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error(f"Failed to get all nodes: {exc}")
        return []


def log_command(
    conn: sqlite3.Connection,
    node_id: str,
    command: str,
    status: str,
    timestamp: str | None = None,
) -> None:
    """Record a command attempt in the audit log."""
    from datetime import datetime, timezone
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "INSERT INTO command_log (node_id, command, status, timestamp) VALUES (?, ?, ?, ?)",
            (node_id, command, status, timestamp),
        )
        conn.commit()
    except sqlite3.Error as exc:
        log.error(f"Failed to log command (node_id={node_id}, cmd={command}): {exc}")


def get_command_log(
    conn: sqlite3.Connection,
    node_id: str | None = None,
    command: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Return command log entries newest-first. Optionally filter by node_id or command."""
    keys = ("id", "node_id", "command", "status", "timestamp")
    conditions, params = [], []
    if node_id:
        conditions.append("node_id = ?")
        params.append(node_id)
    if command:
        conditions.append("command = ?")
        params.append(command)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    try:
        cur = conn.execute(
            f"SELECT id, node_id, command, status, timestamp FROM command_log "
            f"{where} ORDER BY timestamp DESC LIMIT ?",
            (*params, limit),
        )
        return [dict(zip(keys, row)) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error(f"Failed to get command log: {exc}")
        return []


def ban_node(conn: sqlite3.Connection, node_id: str, reason: str | None = None) -> None:
    """Add node_id to the banned list. Idempotent."""
    from datetime import datetime, timezone
    banned_at = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "INSERT INTO banned_nodes (node_id, banned_at, reason) VALUES (?, ?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET banned_at = excluded.banned_at, "
            "reason = COALESCE(excluded.reason, reason)",
            (node_id, banned_at, reason),
        )
        conn.commit()
    except sqlite3.Error as exc:
        log.error(f"Failed to ban node (node_id={node_id}): {exc}")


def unban_node(conn: sqlite3.Connection, node_id: str) -> None:
    """Remove node_id from the banned list. Idempotent."""
    try:
        conn.execute("DELETE FROM banned_nodes WHERE node_id = ?", (node_id,))
        conn.commit()
    except sqlite3.Error as exc:
        log.error(f"Failed to unban node (node_id={node_id}): {exc}")


def is_banned(conn: sqlite3.Connection, node_id: str) -> bool:
    """Return True if node_id is in the banned list."""
    try:
        cur = conn.execute("SELECT 1 FROM banned_nodes WHERE node_id = ?", (node_id,))
        return cur.fetchone() is not None
    except sqlite3.Error as exc:
        log.error(f"Failed to check ban status (node_id={node_id}): {exc}")
        return False


def get_banned_nodes(conn: sqlite3.Connection) -> list[dict]:
    """Return all banned nodes ordered by banned_at descending."""
    keys = ("node_id", "banned_at", "reason")
    try:
        cur = conn.execute(
            "SELECT node_id, banned_at, reason FROM banned_nodes ORDER BY banned_at DESC"
        )
        return [dict(zip(keys, row)) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error(f"Failed to get banned nodes: {exc}")
        return []
