"""
Web UI for MeshtasticBot — read-only log viewer and status dashboard.

Started as a daemon thread from main.py when web.enabled is true in config.yaml.
"""

import json
import logging
import math
import queue
import threading
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for

from db import (
    ban_node,
    get_all_nodes,
    get_banned_nodes,
    get_command_log,
    get_last_message_time,
    get_message_counts,
    get_messages_page,
    get_node_command_summary,
    unban_node,
)

log = logging.getLogger(__name__)

PAGE_SIZE = 50

# ── SSE fan-out ──────────────────────────────────────────────────────────────
_sse_lock = threading.Lock()
_sse_clients: list[queue.SimpleQueue] = []


def push_event(event_type: str, data: dict) -> None:
    """Push a server-sent event to all connected SSE clients."""
    payload = json.dumps(data, default=str)
    frame = f"event: {event_type}\ndata: {payload}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(frame)
            except Exception:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


def create_app(db_conn, bot_state: dict, admin_username: str = "", admin_password: str = "") -> Flask:
    app = Flask(__name__)
    app.config["db_conn"] = db_conn
    app.config["bot_state"] = bot_state
    app.config["admin_username"] = admin_username
    app.config["admin_password"] = admin_password

    def require_admin(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth = request.authorization
            if (
                not auth
                or auth.username != app.config["admin_username"]
                or auth.password != app.config["admin_password"]
            ):
                return Response(
                    "Admin authentication required.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="MeshtasticBot Admin"'},
                )
            return f(*args, **kwargs)
        return decorated

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

    @app.route("/nodes")
    def nodes():
        conn = app.config["db_conn"]
        q = request.args.get("q", "").strip()
        rows = get_all_nodes(conn, query=q or None) if conn else []
        return render_template("nodes.html", rows=rows, q=q)

    @app.route("/audit")
    @require_admin
    def audit():
        conn = app.config["db_conn"]
        node_filter = request.args.get("node", "").strip()
        cmd_filter = request.args.get("cmd", "").strip()
        rows = get_command_log(conn, node_id=node_filter or None, command=cmd_filter or None) if conn else []
        banned = get_banned_nodes(conn) if conn else []
        banned_ids = {r["node_id"] for r in banned}
        summary = get_node_command_summary(conn) if conn else []
        return render_template(
            "audit.html",
            rows=rows,
            banned_ids=banned_ids,
            node_filter=node_filter,
            cmd_filter=cmd_filter,
            summary=summary,
        )

    @app.route("/audit/ban", methods=["POST"])
    @require_admin
    def audit_ban():
        conn = app.config["db_conn"]
        node_id = request.form.get("node_id", "").strip()
        reason = request.form.get("reason", "").strip() or None
        if node_id and conn:
            ban_node(conn, node_id, reason=reason)
        return redirect(url_for("audit"))

    @app.route("/audit/unban", methods=["POST"])
    @require_admin
    def audit_unban():
        conn = app.config["db_conn"]
        node_id = request.form.get("node_id", "").strip()
        if node_id and conn:
            unban_node(conn, node_id)
        return redirect(url_for("audit"))

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

    @app.route("/health")
    def health():
        conn = app.config["db_conn"]
        state = app.config["bot_state"]
        start_time = state.get("start_time")
        uptime = (
            int((datetime.now(tz=timezone.utc) - start_time).total_seconds())
            if start_time
            else None
        )
        db_size = conn.execute(
            "SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()"
        ).fetchone()[0]
        return jsonify({
            "connected": bool(state.get("connected", False)),
            "uptime_seconds": uptime,
            "last_message_at": get_last_message_time(conn),
            "db_size_bytes": db_size,
        })

    @app.route("/api/nodes")
    def api_nodes():
        conn = app.config["db_conn"]
        nodes = get_all_nodes(conn) if conn else []
        return jsonify({"nodes": nodes})

    @app.route("/api/events")
    def sse():
        def stream():
            client_q: queue.SimpleQueue = queue.SimpleQueue()
            with _sse_lock:
                _sse_clients.append(client_q)
            try:
                yield "event: heartbeat\ndata: {}\n\n"
                while True:
                    try:
                        msg = client_q.get(timeout=25)
                        yield msg
                    except queue.Empty:
                        yield "event: heartbeat\ndata: {}\n\n"
            finally:
                with _sse_lock:
                    try:
                        _sse_clients.remove(client_q)
                    except ValueError:
                        pass

        return Response(
            stream(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/map")
    def map_view():
        return render_template("map.html")

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


def start_web_server(db_conn, bot_state: dict, port: int = 8080, admin_username: str = "", admin_password: str = ""):
    """Start the Flask web server in a background daemon thread."""
    app = create_app(db_conn, bot_state, admin_username=admin_username, admin_password=admin_password)

    def run():
        log.info(f"Web UI starting on http://0.0.0.0:{port}")
        # Use werkzeug directly to suppress the dev-server warning
        from werkzeug.serving import make_server
        srv = make_server("0.0.0.0", port, app, threaded=True)
        srv.serve_forever()

    t = threading.Thread(target=run, daemon=True, name="web-ui")
    t.start()
