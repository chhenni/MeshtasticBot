"""
Web UI for MeshtasticBot — read-only log viewer and status dashboard.

Started as a daemon thread from main.py when web.enabled is true in config.yaml.
"""

import json
import queue
import threading
from datetime import datetime, timezone
from functools import wraps
from unittest.mock import patch

import structlog
from flask import Flask, Response, jsonify, redirect, render_template, request, url_for

from db import (
    add_privileged_node,
    ban_node,
    get_all_nodes,
    get_banned_nodes,
    get_command_log,
    get_last_message_time,
    get_message_counts,
    get_messages_page,
    get_node,
    get_node_command_summary,
    get_privileged_nodes,
    remove_privileged_node,
    unban_node,
)

log = structlog.get_logger()

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
        before = request.args.get("before", "")
        after = request.args.get("after", "")

        channel = int(channel_raw) if channel_raw.lstrip("-").isdigit() else None
        rows, total = get_messages_page(
            conn, channel,
            date_from or None, date_to or None,
            before=before or None,
            after=after or None,
            page_size=PAGE_SIZE,
        )

        # Cursors for next/prev links — oldest and newest received_at in current page
        oldest = rows[-1]["received_at"] if rows else None
        newest = rows[0]["received_at"] if rows else None
        has_older = len(rows) == PAGE_SIZE
        has_newer = bool(before or after)

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
            oldest=oldest,
            newest=newest,
            has_older=has_older,
            has_newer=has_newer,
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
        before = request.args.get("before", "")
        after = request.args.get("after", "")

        channel = int(channel_raw) if channel_raw.lstrip("-").isdigit() else None
        rows, total = get_messages_page(
            conn, channel,
            date_from or None, date_to or None,
            before=before or None,
            after=after or None,
            page_size=PAGE_SIZE,
        )
        oldest = rows[-1]["received_at"] if rows else None
        newest = rows[0]["received_at"] if rows else None
        return jsonify({
            "total": total,
            "page_size": PAGE_SIZE,
            "has_older": len(rows) == PAGE_SIZE,
            "has_newer": bool(before or after),
            "oldest": oldest,
            "newest": newest,
            "messages": rows,
        })

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

    @app.route("/admin/privileged")
    @require_admin
    def privileged_nodes_page():
        conn = app.config["db_conn"]
        priv_nodes = get_privileged_nodes(conn) if conn else []
        all_nodes = get_all_nodes(conn) if conn else []
        return render_template("privileged.html", rows=priv_nodes, all_nodes=all_nodes)

    @app.route("/admin/privileged/add", methods=["POST"])
    @require_admin
    def privileged_add():
        conn = app.config["db_conn"]
        node_id = request.form.get("node_id", "").strip()
        if node_id and conn:
            node = get_node(conn, node_id)
            pub_key = node.get("public_key") if node else None
            add_privileged_node(conn, node_id, added_by="web", public_key=pub_key)
            push_event("privilege_update", {"action": "add", "node_id": node_id})
        return redirect("/admin/privileged")

    @app.route("/admin/privileged/remove", methods=["POST"])
    @require_admin
    def privileged_remove():
        conn = app.config["db_conn"]
        node_id = request.form.get("node_id", "").strip()
        if node_id and conn:
            remove_privileged_node(conn, node_id)
            push_event("privilege_update", {"action": "remove", "node_id": node_id})
        return redirect("/admin/privileged")

    @app.route("/admin/send", methods=["GET"])
    @require_admin
    def admin_send():
        conn = app.config["db_conn"]
        channel_raw = request.args.get("channel", "")
        node_id = request.args.get("node", "").strip()
        flash_msg = request.args.get("flash", "")
        flash_type = request.args.get("flash_type", "success")

        channel = int(channel_raw) if channel_raw.lstrip("-").isdigit() else None
        all_nodes = get_all_nodes(conn) if conn else []

        # Fetch recent history for the selected context
        history = []
        if channel is not None and conn:
            history, _ = get_messages_page(conn, channel, None, None, page_size=50)
            history = list(reversed(history))  # chronological order for display
        elif node_id and conn:
            history, _ = get_messages_page(conn, -1, None, None, page_size=50, sender_id=node_id)
            history = list(reversed(history))

        return render_template(
            "send.html",
            channel=channel_raw,
            node_id=node_id,
            all_nodes=all_nodes,
            history=history,
            flash_msg=flash_msg,
            flash_type=flash_type,
        )

    @app.route("/admin/send", methods=["POST"])
    @require_admin
    def admin_send_post():
        state = app.config["bot_state"]
        text = request.form.get("text", "").strip()
        target_type = request.form.get("target_type", "channel")
        channel_raw = request.form.get("channel_index", "0").strip()
        dest_node = request.form.get("destination_id", "").strip()

        if not text:
            return Response("Missing message text.", 400)

        send_fn = state.get("send_fn")
        interface = state.get("interface")
        if send_fn is None or interface is None:
            return redirect(url_for("admin_send") + "?flash=Bot+interface+not+available&flash_type=danger")

        try:
            if target_type == "node" and dest_node:
                send_fn(interface, text, destinationId=dest_node, channelIndex=0)
                log.info("web_send", direction="dm", to=dest_node, text=text)
                base = url_for("admin_send")
                return redirect(f"{base}?node={dest_node}&flash=DM+sent+to+{dest_node}&flash_type=success")
            else:
                channel_index = int(channel_raw) if channel_raw.lstrip("-").isdigit() else 0
                send_fn(interface, text, channelIndex=channel_index)
                log.info("web_send", direction="channel", channel=channel_index, text=text)
                base = url_for("admin_send")
                return redirect(
                    f"{base}?channel={channel_index}"
                    f"&flash=Message+sent+to+channel+{channel_index}&flash_type=success"
                )
        except Exception as exc:
            log.error("web_send_failed", error=str(exc))
            return redirect(url_for("admin_send") + f"?flash=Send+failed:+{str(exc)[:80]}&flash_type=danger")

    @app.route("/api/send", methods=["POST"])
    @require_admin
    def api_send():
        state = app.config["bot_state"]
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        channel_index = data.get("channel")
        destination_id = (data.get("destination_id") or "").strip()

        if not text:
            return jsonify({"error": "Missing text"}), 400

        send_fn = state.get("send_fn")
        interface = state.get("interface")
        if send_fn is None or interface is None:
            return jsonify({"error": "Bot interface not available"}), 503

        try:
            if destination_id:
                send_fn(interface, text, destinationId=destination_id, channelIndex=0)
                log.info("web_api_send", direction="dm", to=destination_id, text=text)
                return jsonify({"status": "sent", "direction": "dm", "destination_id": destination_id})
            elif channel_index is not None:
                send_fn(interface, text, channelIndex=int(channel_index))
                log.info("web_api_send", direction="channel", channel=channel_index, text=text)
                return jsonify({"status": "sent", "direction": "channel", "channel": channel_index})
            else:
                return jsonify({"error": "Provide either channel or destination_id"}), 400
        except Exception as exc:
            log.error("web_api_send_failed", error=str(exc))
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/command", methods=["POST"])
    @require_admin
    def api_command():
        from commands import COMMANDS

        data = request.get_json(silent=True) or {}
        text = (data.get("command") or "").strip()
        lat = data.get("lat")
        lon = data.get("lon")

        if not text:
            return jsonify({"error": "Missing command"}), 400

        cmd_name = text.split()[0].lower()
        handler = COMMANDS.get(cmd_name)
        if not handler:
            return jsonify({"error": f"Unknown command: {cmd_name}"}), 400

        position = None
        if lat is not None and lon is not None:
            try:
                position = (float(lat), float(lon))
            except (TypeError, ValueError):
                return jsonify({"error": "lat and lon must be numbers"}), 400

        state = app.config["bot_state"]
        conn = app.config["db_conn"]

        ctx = {
            "interface": state.get("interface"),
            "sender": "!api-admin",
            "db_conn": conn,
            "log_channel": state.get("log_channel"),
            "start_time": state.get("start_time"),
            "county": state.get("county"),
            "flipper_cfg": state.get("flipper_cfg"),
            "position": position,
        }

        replies: list[str] = []
        with patch("commands.time"):
            handler(text, replies.append, ctx)

        return jsonify({"command": text, "replies": replies})

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
        log.info("web_server_starting", port=port)
        # Use werkzeug directly to suppress the dev-server warning
        from werkzeug.serving import make_server
        srv = make_server("0.0.0.0", port, app, threaded=True)
        srv.serve_forever()

    t = threading.Thread(target=run, daemon=True, name="web-ui")
    t.start()
