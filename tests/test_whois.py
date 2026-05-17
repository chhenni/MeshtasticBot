"""
Tests for handle_whois_command.
"""

import pytest

from commands import handle_whois_command
from db import init_db, upsert_node

TS = "2026-05-18T00:00:00+00:00"


@pytest.fixture
def conn():
    c = init_db(":memory:")
    upsert_node(c, "!aabbccdd", long_name="Alpha Node", short_name="AL",
                last_seen=TS, snr=7.5, rssi=-85, lat=59.91, lon=10.75)
    upsert_node(c, "!11223344", long_name="Beta Node", short_name="BT",
                last_seen=TS, snr=3.0, rssi=-95)
    return c


def run(text, conn):
    replies = []
    ctx = {"db_conn": conn, "interface": None, "sender": "!xyz",
           "log_channel": None, "start_time": None, "county": None}
    handle_whois_command(text, replies.append, ctx)
    return replies


class TestWhoisCommand:
    def test_exact_id_lookup(self, conn):
        replies = run("/whois !aabbccdd", conn)
        combined = "\n".join(replies)
        assert "Alpha Node" in combined

    def test_exact_id_shows_snr(self, conn):
        replies = run("/whois !aabbccdd", conn)
        assert any("7.5" in r for r in replies)

    def test_exact_id_shows_last_seen(self, conn):
        replies = run("/whois !aabbccdd", conn)
        combined = "\n".join(replies)
        assert "2026" in combined

    def test_name_search_single_match(self, conn):
        replies = run("/whois alpha", conn)
        assert any("Alpha Node" in r for r in replies)

    def test_name_search_multiple_matches(self, conn):
        replies = run("/whois node", conn)
        combined = "\n".join(replies)
        assert "Alpha Node" in combined
        assert "Beta Node" in combined

    def test_unknown_id_returns_not_found(self, conn):
        replies = run("/whois !deadbeef", conn)
        assert len(replies) == 1
        assert "ikke funnet" in replies[0].lower() or "not found" in replies[0].lower() or "Ingen" in replies[0]

    def test_unknown_name_returns_not_found(self, conn):
        replies = run("/whois zzz", conn)
        assert len(replies) == 1
        assert "Ingen" in replies[0] or "ikke funnet" in replies[0].lower()

    def test_no_args_returns_usage(self, conn):
        replies = run("/whois", conn)
        assert len(replies) == 1
        assert "/whois" in replies[0]

    def test_no_db_returns_error(self):
        replies = run("/whois !abc", conn=None)
        assert len(replies) == 1
        assert "ikke aktivert" in replies[0]
