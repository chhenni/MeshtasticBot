"""
Web UI for MeshtasticBot — read-only log viewer and status dashboard.

Started as a daemon thread from main.py when web.enabled is true in config.yaml.
"""

import logging
import math
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

from db import get_message_counts, get_messages_page

log = logging.getLogger(__name__)

PAGE_SIZE = 50


def create_app(db_conn, bot_state: dict) -> Flask:
    app = Flask(__name__)
    app.config["db_conn"] = db_conn
    app.config["bot_state"] = bot_state

    @app.route("/")
    def logs():
        conn = app.config["db_conn"]
        channel_raw = request.args.get("channel", "")
        date_from = request.args.get("from", "")
        date_to = request.args.get("to", "")
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1

        channel = int(channel_raw) if channel_raw.lstrip("-").isdigit() else None
        rows, total = get_messages_page(conn, channel, date_from or None, date_to or None, page, PAGE_SIZE)
        total_pages = max(1, math.ceil(total / PAGE_SIZE))

        # Distinct channels for the filter dropdown
        try:
            ch_rows = conn.execute(
                "SELECT DISTINCT channel FROM messages ORDER BY channel"
            ).fetchall()
            channels = [r[0] for r in ch_rows]
        except Exception:
            channels = []

        return render_template(
            "logs.html",
            rows=rows,
            total=total,
            page=page,
            total_pages=total_pages,
            channel=channel_raw,
            date_from=date_from,
            date_to=date_to,
            channels=channels,
        )

    @app.route("/status")
    def status():
        conn = app.config["db_conn"]
        state = app.config["bot_state"]
        counts = get_message_counts(conn) if conn else {"total": 0, "last_24h": 0, "by_channel": {}}
        uptime = _format_uptime(state.get("start_time"))
        return render_template(
            "status.html",
            state=state,
            counts=counts,
            uptime=uptime,
        )

    @app.route("/api/messages")
    def api_messages():
        conn = app.config["db_conn"]
        channel_raw = request.args.get("channel", "")
        date_from = request.args.get("from", "")
        date_to = request.args.get("to", "")
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1

        channel = int(channel_raw) if channel_raw.lstrip("-").isdigit() else None
        rows, total = get_messages_page(conn, channel, date_from or None, date_to or None, page, PAGE_SIZE)
        return jsonify({"total": total, "page": page, "page_size": PAGE_SIZE, "messages": rows})

    return app


def _format_uptime(start_time: datetime | None) -> str:
    if start_time is None:
        return "unknown"
    delta = datetime.now(tz=timezone.utc) - start_time
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def start_web_server(db_conn, bot_state: dict, port: int = 8080):
    """Start the Flask web server in a background daemon thread."""
    app = create_app(db_conn, bot_state)

    def run():
        log.info(f"Web UI starting on http://0.0.0.0:{port}")
        # Use werkzeug directly to suppress the dev-server warning
        from werkzeug.serving import make_server
        srv = make_server("0.0.0.0", port, app)
        srv.serve_forever()

    t = threading.Thread(target=run, daemon=True, name="web-ui")
    t.start()
