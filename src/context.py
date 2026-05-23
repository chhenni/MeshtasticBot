"""
Shared type definitions for MeshtasticBot command handlers.
"""

import sqlite3
from datetime import datetime
from typing import Optional, TypedDict


class BotContext(TypedDict):
    """Context dict passed to every command handler.

    Keys
    ----
    interface   Meshtastic interface object (for GPS lookups, sending).
                None when running in tests without a real device.
    sender      Node ID of the message sender (e.g. "!aabbccdd").
    db_conn     SQLite connection, or None if DB is unavailable.
    log_channel Channel index for the /krslog command, or None.
    start_time  UTC datetime when the bot started, or None.
    county      Norwegian fylkesnummer for weather alerts, or None.
    flipper_cfg Flipper Zero config dict, or None if not configured.
                Keys: "device" (str), "commands" (dict[str, str]).
    """

    interface: Optional[object]
    sender: str
    db_conn: Optional[sqlite3.Connection]
    log_channel: Optional[int]
    start_time: Optional[datetime]
    county: Optional[str]
    flipper_cfg: Optional[dict]
