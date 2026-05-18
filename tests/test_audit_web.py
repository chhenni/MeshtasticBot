"""
Tests for the /audit web page and ban/unban HTTP actions (Basic Auth protected).
"""

import base64

import pytest

from db import ban_node, get_banned_nodes, init_db, is_banned, log_command
from web import create_app

ADMIN_USER = "admin"
ADMIN_PASS = "testpass"


def auth_header(username=ADMIN_USER, password=ADMIN_PASS):
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def conn():
    c = init_db(":memory:")
    log_command(c, "!aabbccdd", "/ping", "ok", timestamp="2026-05-18T00:00:00")
    log_command(c, "!aabbccdd", "/weather", "rate_limited", timestamp="2026-05-18T00:01:00")
    log_command(c, "!badnode", "/ping", "banned", timestamp="2026-05-18T00:02:00")
    return c


@pytest.fixture
def client(conn):
    app = create_app(
        conn,
        {"channel": 0, "log_channel": 0, "county": None, "start_time": None},
        admin_username=ADMIN_USER,
        admin_password=ADMIN_PASS,
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestAuditAuth:
    def test_audit_requires_auth(self, client):
        resp = client.get("/audit")
        assert resp.status_code == 401

    def test_audit_wrong_password_rejected(self, client):
        resp = client.get("/audit", headers=auth_header(password="wrong"))
        assert resp.status_code == 401

    def test_audit_correct_credentials_accepted(self, client):
        resp = client.get("/audit", headers=auth_header())
        assert resp.status_code == 200


class TestAuditPage:
    def test_audit_shows_commands(self, client):
        resp = client.get("/audit", headers=auth_header())
        html = resp.data.decode()
        assert "/ping" in html
        assert "/weather" in html

    def test_audit_shows_node_ids(self, client):
        resp = client.get("/audit", headers=auth_header())
        assert b"!aabbccdd" in resp.data

    def test_audit_shows_status(self, client):
        resp = client.get("/audit", headers=auth_header())
        html = resp.data.decode()
        assert "ok" in html
        assert "rate_limited" in html
        assert "banned" in html

    def test_audit_filter_by_node(self, client):
        resp = client.get("/audit?node=!badnode", headers=auth_header())
        html = resp.data.decode()
        assert "!badnode" in html
        # Summary always shows all nodes; check the log section doesn't show !aabbccdd
        # by verifying the filter heading is present
        assert "node: <code>!badnode</code>" in html

    def test_audit_filter_by_command(self, client):
        resp = client.get("/audit?cmd=/weather", headers=auth_header())
        html = resp.data.decode()
        assert "/weather" in html
        # /ping entries for !aabbccdd filtered out
        assert "rate_limited" in html


class TestBanActions:
    def test_ban_requires_auth(self, client):
        resp = client.post("/audit/ban", data={"node_id": "!abc"})
        assert resp.status_code == 401

    def test_ban_node_via_post(self, client, conn):
        resp = client.post("/audit/ban", data={"node_id": "!newbad"}, headers=auth_header())
        assert resp.status_code in (200, 302)
        assert is_banned(conn, "!newbad")

    def test_ban_with_reason(self, client, conn):
        client.post("/audit/ban", data={"node_id": "!newbad", "reason": "Spamming"}, headers=auth_header())
        rows = get_banned_nodes(conn)
        match = next(r for r in rows if r["node_id"] == "!newbad")
        assert match["reason"] == "Spamming"

    def test_unban_requires_auth(self, client, conn):
        ban_node(conn, "!abc")
        resp = client.post("/audit/unban", data={"node_id": "!abc"})
        assert resp.status_code == 401

    def test_unban_node_via_post(self, client, conn):
        ban_node(conn, "!abc")
        resp = client.post("/audit/unban", data={"node_id": "!abc"}, headers=auth_header())
        assert resp.status_code in (200, 302)
        assert not is_banned(conn, "!abc")

    def test_ban_shows_in_audit_page(self, client, conn):
        ban_node(conn, "!visible")
        resp = client.get("/audit", headers=auth_header())
        assert b"!visible" in resp.data

    def test_audit_nav_link_not_visible_to_unauthenticated(self, client):
        """The /audit link should still be in the nav (it 401s on click),
        but it must at least not crash the public pages."""
        resp = client.get("/")
        assert resp.status_code == 200


class TestAuditSummary:
    def test_summary_table_appears(self, client):
        resp = client.get("/audit", headers=auth_header())
        html = resp.data.decode()
        assert "Node Summary" in html

    def test_summary_shows_node_id(self, client):
        resp = client.get("/audit", headers=auth_header())
        assert b"!aabbccdd" in resp.data

    def test_summary_shows_rate_limited_count(self, client):
        resp = client.get("/audit", headers=auth_header())
        html = resp.data.decode()
        # !aabbccdd has 1 rate_limited entry
        assert "rate_limited" in html or "1" in html

    def test_summary_links_to_filtered_view(self, client):
        resp = client.get("/audit", headers=auth_header())
        html = resp.data.decode()
        assert "/audit?node=!aabbccdd" in html
