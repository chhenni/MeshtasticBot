"""
SQLite persistence layer for MeshtasticBot.

Provides init_db() to open/create the database and store_message() to persist
received channel messages with deduplication by packet ID.
"""

import os
import sqlite3

import structlog

log = structlog.get_logger()

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

CREATE_PRIVILEGED_NODES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS privileged_nodes (
    node_id     TEXT    PRIMARY KEY,
    public_key  TEXT,
    added_at    TEXT    NOT NULL,
    added_by    TEXT    NOT NULL
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
    conn.execute(CREATE_PRIVILEGED_NODES_TABLE_SQL)
    # Migration: add public_key to nodes if upgrading from older schema
    try:
        conn.execute("ALTER TABLE nodes ADD COLUMN public_key TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    log.info("db_opened", path=path)
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
        log.error("query_messages_failed", error=str(exc))
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
        log.error("query_last_messages_failed", error=str(exc))
        return []


def get_messages_page(
    conn: sqlite3.Connection,
    channel: int | None,
    date_from: str | None,
    date_to: str | None,
    before: str | None = None,
    after: str | None = None,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """Return a page of messages using keyset pagination.

    *before* / *after* are ISO-8601 ``received_at`` cursors from the previous
    page.  Pass *before* to go to an older page, *after* to go to a newer one.
    Also returns the total filtered count for display in the header.
    """
    conditions = []
    params: list = []

    if channel is not None:
        conditions.append("m.channel = ?")
        params.append(channel)
    if date_from:
        conditions.append("m.received_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("m.received_at <= ?")
        params.append(date_to + "T23:59:59")

    # Keyset cursors
    if before:
        conditions.append("m.received_at < ?")
        params.append(before)
    if after:
        conditions.append("m.received_at > ?")
        params.append(after)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Total uses only the filter conditions (not cursor) for the header count
    filter_conditions = [c for c in conditions if "< ?" not in c and "> ?" not in c]
    filter_params = params[: len(filter_conditions)]
    count_where = ("WHERE " + " AND ".join(c.replace("m.", "") for c in filter_conditions)) if filter_conditions else ""

    try:
        total = conn.execute(f"SELECT COUNT(*) FROM messages {count_where}", filter_params).fetchone()[0]

        if after:
            # When paging forward ("newer"), fetch ascending then reverse so newest is first
            cur = conn.execute(
                f"SELECT m.channel, m.sender_id, m.text, m.received_at, "
                f"n.long_name, n.short_name "
                f"FROM messages m LEFT JOIN nodes n ON m.sender_id = n.node_id "
                f"{where} "
                f"ORDER BY m.received_at ASC LIMIT ?",
                params + [page_size],
            )
            rows_raw = list(reversed(cur.fetchall()))
        else:
            cur = conn.execute(
                f"SELECT m.channel, m.sender_id, m.text, m.received_at, "
                f"n.long_name, n.short_name "
                f"FROM messages m LEFT JOIN nodes n ON m.sender_id = n.node_id "
                f"{where} "
                f"ORDER BY m.received_at DESC LIMIT ?",
                params + [page_size],
            )
            rows_raw = cur.fetchall()

        rows = [
            {
                "channel": r[0], "sender_id": r[1], "text": r[2], "received_at": r[3],
                "long_name": r[4], "short_name": r[5],
            }
            for r in rows_raw
        ]
        return rows, total
    except sqlite3.Error as exc:
        log.error("query_messages_page_failed", error=str(exc))
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
        log.error("get_message_counts_failed", error=str(exc))
        return {"total": 0, "last_24h": 0, "by_channel": {}}


def get_last_message_time(conn: sqlite3.Connection) -> str | None:
    """Return the received_at timestamp of the most recent message, or None."""
    try:
        row = conn.execute("SELECT MAX(received_at) FROM messages").fetchone()
        return row[0] if row else None
    except sqlite3.Error as exc:
        log.error("get_last_message_time_failed", error=str(exc))
        return None


def purge_old_messages(conn: sqlite3.Connection, days: int = 365) -> int:
    """Delete messages older than *days* days. Returns the number of rows deleted."""
    try:
        cur = conn.execute(
            "DELETE FROM messages WHERE received_at < datetime('now', ? || ' days')",
            (f"-{days}",),
        )
        conn.commit()
        if cur.rowcount:
            log.info("db_purged", rows=cur.rowcount, older_than_days=days)
        return cur.rowcount
    except sqlite3.Error as exc:
        log.error("db_purge_failed", error=str(exc))
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
        log.error("store_message_failed", packet_id=packet_id, error=str(exc))


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
    public_key: str | None = None,
) -> None:
    """Insert or update a node record, only overwriting non-None fields."""
    if not node_id:
        log.warning("upsert_node_skipped", reason="empty_node_id")
        return
    try:
        conn.execute(
            "INSERT INTO nodes "
            "(node_id, long_name, short_name, last_seen, last_snr, last_rssi, lat, lon, public_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET "
            "  long_name  = COALESCE(excluded.long_name,  long_name), "
            "  short_name = COALESCE(excluded.short_name, short_name), "
            "  last_seen  = COALESCE(excluded.last_seen,  last_seen), "
            "  last_snr   = COALESCE(excluded.last_snr,   last_snr), "
            "  last_rssi  = COALESCE(excluded.last_rssi,  last_rssi), "
            "  lat        = COALESCE(excluded.lat,        lat), "
            "  lon        = COALESCE(excluded.lon,        lon), "
            "  public_key = COALESCE(excluded.public_key, public_key)",
            (node_id, long_name, short_name, last_seen, snr, rssi, lat, lon, public_key),
        )
        conn.commit()
    except sqlite3.Error as exc:
        log.error("upsert_node_failed", node_id=node_id, error=str(exc))


def get_node(conn: sqlite3.Connection, node_id: str) -> dict | None:
    """Return a node record by exact node_id, or None if not found."""
    try:
        cur = conn.execute(
            "SELECT node_id, long_name, short_name, last_seen, last_snr, last_rssi, lat, lon, public_key "
            "FROM nodes WHERE node_id = ?",
            (node_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        keys = ("node_id", "long_name", "short_name", "last_seen", "last_snr", "last_rssi", "lat", "lon", "public_key")
        return dict(zip(keys, row))
    except sqlite3.Error as exc:
        log.error("get_node_failed", node_id=node_id, error=str(exc))
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
        log.error("lookup_nodes_failed", query=query, error=str(exc))
        return []


def get_all_nodes(conn: sqlite3.Connection, query: str | None = None) -> list[dict]:
    """Return all nodes sorted by last_seen descending. Optionally filter by *query*."""
    keys = ("node_id", "long_name", "short_name", "last_seen", "last_snr", "last_rssi", "lat", "lon", "public_key")
    try:
        if query:
            pattern = f"%{query}%"
            cur = conn.execute(
                "SELECT node_id, long_name, short_name, last_seen, last_snr, last_rssi, lat, lon, public_key "
                "FROM nodes WHERE node_id LIKE ? OR long_name LIKE ? OR short_name LIKE ? "
                "ORDER BY last_seen DESC",
                (pattern, pattern, pattern),
            )
        else:
            cur = conn.execute(
                "SELECT node_id, long_name, short_name, last_seen, last_snr, last_rssi, lat, lon, public_key "
                "FROM nodes ORDER BY last_seen DESC"
            )
        return [dict(zip(keys, row)) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error("get_all_nodes_failed", error=str(exc))
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
        log.error("log_command_failed", node_id=node_id, cmd=command, error=str(exc))


def get_command_log(
    conn: sqlite3.Connection,
    node_id: str | None = None,
    command: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Return command log entries newest-first. Optionally filter by node_id or command."""
    keys = ("id", "node_id", "command", "status", "timestamp", "long_name", "short_name")
    conditions, params = [], []
    if node_id:
        conditions.append("cl.node_id = ?")
        params.append(node_id)
    if command:
        conditions.append("cl.command = ?")
        params.append(command)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    try:
        cur = conn.execute(
            f"SELECT cl.id, cl.node_id, cl.command, cl.status, cl.timestamp, "
            f"n.long_name, n.short_name "
            f"FROM command_log cl LEFT JOIN nodes n ON cl.node_id = n.node_id "
            f"{where} ORDER BY cl.timestamp DESC LIMIT ?",
            (*params, limit),
        )
        return [dict(zip(keys, row)) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error("get_command_log_failed", error=str(exc))
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
        log.error("ban_node_failed", node_id=node_id, error=str(exc))


def unban_node(conn: sqlite3.Connection, node_id: str) -> None:
    """Remove node_id from the banned list. Idempotent."""
    try:
        conn.execute("DELETE FROM banned_nodes WHERE node_id = ?", (node_id,))
        conn.commit()
    except sqlite3.Error as exc:
        log.error("unban_node_failed", node_id=node_id, error=str(exc))


def is_banned(conn: sqlite3.Connection, node_id: str) -> bool:
    """Return True if node_id is in the banned list."""
    try:
        cur = conn.execute("SELECT 1 FROM banned_nodes WHERE node_id = ?", (node_id,))
        return cur.fetchone() is not None
    except sqlite3.Error as exc:
        log.error("check_ban_failed", node_id=node_id, error=str(exc))
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
        log.error("get_banned_nodes_failed", error=str(exc))
        return []


def get_node_command_summary(conn: sqlite3.Connection) -> list[dict]:
    """Return per-node command stats: total, today, week, rate_limited, last_seen, long_name, short_name.

    Sorted by total commands descending.
    """
    keys = ("node_id", "total", "today", "week", "rate_limited", "last_seen", "long_name", "short_name")
    try:
        cur = conn.execute(
            """
            SELECT
                cl.node_id,
                COUNT(*)                                                              AS total,
                COUNT(CASE WHEN cl.timestamp >= datetime('now', '-1 day')  THEN 1 END) AS today,
                COUNT(CASE WHEN cl.timestamp >= datetime('now', '-7 days') THEN 1 END) AS week,
                COUNT(CASE WHEN cl.status = 'rate_limited'                 THEN 1 END) AS rate_limited,
                MAX(cl.timestamp)                                                     AS last_seen,
                n.long_name,
                n.short_name
            FROM command_log cl LEFT JOIN nodes n ON cl.node_id = n.node_id
            GROUP BY cl.node_id
            ORDER BY total DESC
            """
        )
        return [dict(zip(keys, row)) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error("get_node_command_summary_failed", error=str(exc))
        return []


# ── Privileged nodes ──────────────────────────────────────────────────────────


def add_privileged_node(
    conn: sqlite3.Connection,
    node_id: str,
    added_by: str,
    public_key: str | None = None,
) -> None:
    """Add node_id to the privileged list. Idempotent — updates key if already present."""
    from datetime import datetime, timezone
    added_at = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "INSERT INTO privileged_nodes (node_id, public_key, added_at, added_by) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET "
            "  public_key = COALESCE(excluded.public_key, public_key), "
            "  added_at   = excluded.added_at, "
            "  added_by   = excluded.added_by",
            (node_id, public_key, added_at, added_by),
        )
        conn.commit()
    except sqlite3.Error as exc:
        log.error("add_privileged_node_failed", node_id=node_id, error=str(exc))


def remove_privileged_node(conn: sqlite3.Connection, node_id: str) -> None:
    """Remove node_id from the privileged list. Idempotent."""
    try:
        conn.execute("DELETE FROM privileged_nodes WHERE node_id = ?", (node_id,))
        conn.commit()
    except sqlite3.Error as exc:
        log.error("remove_privileged_node_failed", node_id=node_id, error=str(exc))


def get_privileged_nodes(conn: sqlite3.Connection) -> list[dict]:
    """Return all privileged nodes joined with nodes table for display info.

    Includes a 'key_status' field: 'match', 'mismatch', 'unverified' (no key stored),
    or 'unknown' (node not yet seen on mesh).
    """
    keys = (
        "node_id", "public_key", "added_at", "added_by",
        "long_name", "short_name", "key_status",
    )
    try:
        cur = conn.execute(
            """
            SELECT
                p.node_id,
                p.public_key,
                p.added_at,
                p.added_by,
                n.long_name,
                n.short_name,
                CASE
                    WHEN p.public_key IS NULL              THEN 'unverified'
                    WHEN n.public_key IS NULL              THEN 'unknown'
                    WHEN p.public_key = n.public_key       THEN 'match'
                    ELSE                                        'mismatch'
                END AS key_status
            FROM privileged_nodes p
            LEFT JOIN nodes n ON p.node_id = n.node_id
            ORDER BY p.added_at DESC
            """
        )
        return [dict(zip(keys, row)) for row in cur.fetchall()]
    except sqlite3.Error as exc:
        log.error("get_privileged_nodes_failed", error=str(exc))
        return []


def is_privileged(
    conn: sqlite3.Connection,
    node_id: str,
    public_key: str | None = None,
) -> bool:
    """Return True if node_id is privileged.

    If *public_key* is provided AND a key is stored for this node, the keys
    must match. If no key is stored, node_id membership alone is sufficient.
    """
    try:
        cur = conn.execute(
            "SELECT public_key FROM privileged_nodes WHERE node_id = ?",
            (node_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        stored_key = row[0]
        if stored_key is not None and public_key is not None:
            return stored_key == public_key
        return True
    except sqlite3.Error as exc:
        log.error("check_privilege_failed", node_id=node_id, error=str(exc))
        return False
