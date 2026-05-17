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
