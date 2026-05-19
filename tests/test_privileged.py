"""
Tests for the privileged nodes system:
- db.py functions (add, remove, get, is_privileged)
- web /admin/privileged routes
- dispatcher privilege gate
- /addpriv and /removepriv command handlers
"""


import pytest

from db import (
    add_privileged_node,
    get_privileged_nodes,
    init_db,
    is_privileged,
    remove_privileged_node,
    upsert_node,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    conn = init_db(":memory:")
    return conn


@pytest.fixture
def app_client(db):
    import sys
    sys.path.insert(0, "src")
    from web import create_app
    bot_state = {"connected": True, "start_time": None}
    flask_app = create_app(
        db_conn=db,
        bot_state=bot_state,
        admin_username="admin",
        admin_password="secret",
    )
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


def _auth_headers():
    import base64
    creds = base64.b64encode(b"admin:secret").decode()
    return {"Authorization": f"Basic {creds}"}


# ── DB: add / remove / get / is_privileged ────────────────────────────────────


class TestPrivilegedDb:
    def test_add_and_retrieve(self, db):
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key="key123")
        rows = get_privileged_nodes(db)
        assert len(rows) == 1
        assert rows[0]["node_id"] == "!aabbccdd"
        assert rows[0]["public_key"] == "key123"
        assert rows[0]["added_by"] == "web"

    def test_add_without_key(self, db):
        add_privileged_node(db, "!aabbccdd", added_by="web")
        rows = get_privileged_nodes(db)
        assert rows[0]["public_key"] is None

    def test_add_is_idempotent(self, db):
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key="key1")
        add_privileged_node(db, "!aabbccdd", added_by="mesh", public_key="key2")
        rows = get_privileged_nodes(db)
        assert len(rows) == 1
        assert rows[0]["public_key"] == "key2"
        assert rows[0]["added_by"] == "mesh"

    def test_remove(self, db):
        add_privileged_node(db, "!aabbccdd", added_by="web")
        remove_privileged_node(db, "!aabbccdd")
        assert get_privileged_nodes(db) == []

    def test_remove_nonexistent_is_idempotent(self, db):
        remove_privileged_node(db, "!doesnotexist")  # should not raise

    def test_is_privileged_true(self, db):
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key="mykey")
        assert is_privileged(db, "!aabbccdd", "mykey") is True

    def test_is_privileged_false_not_in_table(self, db):
        assert is_privileged(db, "!aabbccdd") is False

    def test_is_privileged_key_mismatch(self, db):
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key="correctkey")
        assert is_privileged(db, "!aabbccdd", "wrongkey") is False

    def test_is_privileged_no_stored_key_accepts_any(self, db):
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key=None)
        assert is_privileged(db, "!aabbccdd", "anykey") is True
        assert is_privileged(db, "!aabbccdd") is True

    def test_key_status_match(self, db):
        upsert_node(db, "!aabbccdd", last_seen="2025-01-01T00:00:00", public_key="k1")
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key="k1")
        rows = get_privileged_nodes(db)
        assert rows[0]["key_status"] == "match"

    def test_key_status_mismatch(self, db):
        upsert_node(db, "!aabbccdd", last_seen="2025-01-01T00:00:00", public_key="k_new")
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key="k_old")
        rows = get_privileged_nodes(db)
        assert rows[0]["key_status"] == "mismatch"

    def test_key_status_unverified(self, db):
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key=None)
        rows = get_privileged_nodes(db)
        assert rows[0]["key_status"] == "unverified"

    def test_key_status_unknown(self, db):
        # Node privileged but never seen on mesh
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key="k1")
        rows = get_privileged_nodes(db)
        assert rows[0]["key_status"] == "unknown"


# ── Web routes ────────────────────────────────────────────────────────────────


class TestPrivilegedWebRoutes:
    def test_list_requires_auth(self, app_client):
        r = app_client.get("/admin/privileged")
        assert r.status_code == 401

    def test_list_empty(self, app_client):
        r = app_client.get("/admin/privileged", headers=_auth_headers())
        assert r.status_code == 200
        assert b"No privileged nodes" in r.data

    def test_add_node(self, app_client, db):
        upsert_node(db, "!aabbccdd", last_seen="2025-01-01T00:00:00", public_key="pk1")
        r = app_client.post(
            "/admin/privileged/add",
            data={"node_id": "!aabbccdd"},
            headers=_auth_headers(),
        )
        assert r.status_code == 302
        rows = get_privileged_nodes(db)
        assert len(rows) == 1
        assert rows[0]["node_id"] == "!aabbccdd"
        assert rows[0]["public_key"] == "pk1"

    def test_add_unknown_node(self, app_client, db):
        r = app_client.post(
            "/admin/privileged/add",
            data={"node_id": "!deadbeef"},
            headers=_auth_headers(),
        )
        assert r.status_code == 302
        rows = get_privileged_nodes(db)
        assert rows[0]["node_id"] == "!deadbeef"
        assert rows[0]["public_key"] is None

    def test_remove_node(self, app_client, db):
        add_privileged_node(db, "!aabbccdd", added_by="web")
        r = app_client.post(
            "/admin/privileged/remove",
            data={"node_id": "!aabbccdd"},
            headers=_auth_headers(),
        )
        assert r.status_code == 302
        assert get_privileged_nodes(db) == []

    def test_list_shows_node(self, app_client, db):
        add_privileged_node(db, "!aabbccdd", added_by="web", public_key="pk1")
        r = app_client.get("/admin/privileged", headers=_auth_headers())
        assert b"!aabbccdd" in r.data

    def test_add_requires_auth(self, app_client):
        r = app_client.post("/admin/privileged/add", data={"node_id": "!aabbccdd"})
        assert r.status_code == 401

    def test_remove_requires_auth(self, app_client):
        r = app_client.post("/admin/privileged/remove", data={"node_id": "!aabbccdd"})
        assert r.status_code == 401


# ── Dispatcher privilege gate ─────────────────────────────────────────────────


class TestPrivilegeGate:
    def _make_handler(self, db):
        import sys
        sys.path.insert(0, "src")
        from main import make_receive_handler

        replies = []

        class FakeInterface:
            nodes = {}
            def sendText(self, *a, **kw): pass

        handler = make_receive_handler(
            interface=FakeInterface(),
            channel=0,
            db_conn=db,
            log_channel=0,
            bot_state={"start_time": None, "county": "03",
                       "bucket_size": 10, "refill_rate": 1,
                       "admin_username": "", "admin_password": ""},
            bucket_size=100,
            refill_rate=10,
        )
        return handler, replies, FakeInterface()

    def _packet(self, text, sender="!unprivileged"):
        return {
            "decoded": {"text": text},
            "fromId": sender,
            "toId": "^all",
            "channel": 0,
        }

    def test_privileged_cmd_blocked_for_unprivileged(self, db):
        handler, _, _ = self._make_handler(db)
        # /addpriv requires privilege — should be silently dropped
        handler(self._packet("/addpriv !target"))
        from db import get_privileged_nodes
        assert get_privileged_nodes(db) == []

    def test_privileged_cmd_blocked_logged(self, db):
        handler, _, _ = self._make_handler(db)
        handler(self._packet("/addpriv !target", sender="!nobody"))
        from db import get_command_log
        log = get_command_log(db, node_id="!nobody")
        assert any(e["status"] == "not_privileged" for e in log)

    def test_privileged_cmd_allowed_for_privileged(self, db):
        add_privileged_node(db, "!boss", added_by="test", public_key=None)
        upsert_node(db, "!target", last_seen="2025-01-01T00:00:00")
        handler, _, _ = self._make_handler(db)
        handler(self._packet("/addpriv !target", sender="!boss"))
        rows = get_privileged_nodes(db)
        node_ids = [r["node_id"] for r in rows]
        assert "!target" in node_ids


# ── /addpriv and /removepriv command handlers ─────────────────────────────────


class TestAddRemovePrivCommands:
    def _ctx(self, db, sender="!boss"):
        return {"db_conn": db, "sender": sender, "interface": None,
                "log_channel": 0, "start_time": None, "county": "03"}

    def test_addpriv_adds_node(self, db):
        from commands import handle_addpriv_command
        upsert_node(db, "!target", last_seen="2025-01-01T00:00:00", public_key="pk1")
        replies = []
        handle_addpriv_command("/addpriv !target", replies.append, self._ctx(db))
        assert len(replies) == 1
        assert "✅" in replies[0]
        assert is_privileged(db, "!target")

    def test_addpriv_stores_public_key(self, db):
        from commands import handle_addpriv_command
        upsert_node(db, "!target", last_seen="2025-01-01T00:00:00", public_key="mykey")
        handle_addpriv_command("/addpriv !target", lambda _: None, self._ctx(db))
        rows = get_privileged_nodes(db)
        assert rows[0]["public_key"] == "mykey"

    def test_addpriv_missing_arg(self, db):
        from commands import handle_addpriv_command
        replies = []
        handle_addpriv_command("/addpriv", replies.append, self._ctx(db))
        assert "Bruk:" in replies[0]

    def test_removepriv_removes_node(self, db):
        from commands import handle_removepriv_command
        add_privileged_node(db, "!target", added_by="test")
        replies = []
        handle_removepriv_command("/removepriv !target", replies.append, self._ctx(db))
        assert "✅" in replies[0]
        assert not is_privileged(db, "!target")

    def test_removepriv_missing_arg(self, db):
        from commands import handle_removepriv_command
        replies = []
        handle_removepriv_command("/removepriv", replies.append, self._ctx(db))
        assert "Bruk:" in replies[0]


class TestHelpVisibility:
    def _ctx(self, db, sender="!user"):
        return {"db_conn": db, "sender": sender, "interface": None,
                "log_channel": 0, "start_time": None, "county": "03"}

    def test_unprivileged_user_does_not_see_priv_commands(self, db):
        from commands import handle_help_command
        replies = []
        handle_help_command("/help", replies.append, self._ctx(db))
        combined = "\n".join(replies)
        assert "/addpriv" not in combined
        assert "/removepriv" not in combined

    def test_privileged_user_sees_priv_commands(self, db):
        from commands import handle_help_command
        add_privileged_node(db, "!admin", added_by="test")
        replies = []
        handle_help_command("/help", replies.append, self._ctx(db, sender="!admin"))
        combined = "\n".join(replies)
        assert "/addpriv" in combined
        assert "/removepriv" in combined

    def test_no_db_does_not_show_priv_commands(self, db):
        from commands import handle_help_command
        ctx = {"db_conn": None, "sender": "!user", "interface": None,
               "log_channel": 0, "start_time": None, "county": "03"}
        replies = []
        handle_help_command("/help", replies.append, ctx)
        combined = "\n".join(replies)
        assert "/addpriv" not in combined
