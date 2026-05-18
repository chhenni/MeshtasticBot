"""Tests for load_config() environment variable overrides."""

import textwrap

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path, content: str) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(content))
    return str(p)


_MINIMAL_YAML = """
channel: 1
connection:
  type: serial
message_log:
  enabled: true
  channel: 0
  db_path: data/messages.db
  retain_days: 365
web:
  enabled: false
  port: 8080
weather:
  enabled: false
  county: 42
  interval_seconds: 3600
admin:
  username: admin
  password: changeme
rate_limit:
  bucket_size: 5
  refill_rate: 0.1
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadConfigEnvOverrides:
    """load_config() applies MESHTASTIC_* env vars on top of the YAML file."""

    def test_no_env_vars_returns_yaml_values(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        monkeypatch.delenv("MESHTASTIC__CHANNEL", raising=False)
        from main import load_config
        cfg = load_config(path)
        assert cfg["channel"] == 1

    def test_override_int(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        monkeypatch.setenv("MESHTASTIC__CHANNEL", "7")
        from main import load_config
        cfg = load_config(path)
        assert cfg["channel"] == 7

    def test_override_nested_string(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        monkeypatch.setenv("MESHTASTIC__CONNECTION__TYPE", "tcp")
        monkeypatch.setenv("MESHTASTIC__CONNECTION__HOST", "192.168.1.50")
        from main import load_config
        cfg = load_config(path)
        assert cfg["connection"]["type"] == "tcp"
        assert cfg["connection"]["host"] == "192.168.1.50"

    def test_override_bool_true_values(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        for truthy in ("1", "true", "True", "yes", "on"):
            monkeypatch.setenv("MESHTASTIC__WEB__ENABLED", truthy)
            from main import load_config
            cfg = load_config(path)
            assert cfg["web"]["enabled"] is True, f"Expected True for {truthy!r}"

    def test_override_bool_false_values(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        for falsy in ("0", "false", "no", "off", "False"):
            monkeypatch.setenv("MESHTASTIC__WEB__ENABLED", falsy)
            from main import load_config
            cfg = load_config(path)
            assert cfg["web"]["enabled"] is False, f"Expected False for {falsy!r}"

    def test_override_float(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        monkeypatch.setenv("MESHTASTIC__RATE_LIMIT__BUCKET_SIZE", "10")
        monkeypatch.setenv("MESHTASTIC__RATE_LIMIT__REFILL_RATE", "0.5")
        from main import load_config
        cfg = load_config(path)
        assert cfg["rate_limit"]["bucket_size"] == 10.0
        assert cfg["rate_limit"]["refill_rate"] == 0.5

    def test_override_admin_credentials(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        monkeypatch.setenv("MESHTASTIC__ADMIN__USERNAME", "ops")
        monkeypatch.setenv("MESHTASTIC__ADMIN__PASSWORD", "s3cr3t")
        from main import load_config
        cfg = load_config(path)
        assert cfg["admin"]["username"] == "ops"
        assert cfg["admin"]["password"] == "s3cr3t"

    def test_override_db_path(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        monkeypatch.setenv("MESHTASTIC__MESSAGE_LOG__DB_PATH", "/data/prod.db")
        from main import load_config
        cfg = load_config(path)
        assert cfg["message_log"]["db_path"] == "/data/prod.db"

    def test_override_web_port(self, tmp_path, monkeypatch):
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        monkeypatch.setenv("MESHTASTIC__WEB__PORT", "9090")
        from main import load_config
        cfg = load_config(path)
        assert cfg["web"]["port"] == 9090

    def test_invalid_int_env_var_is_ignored(self, tmp_path, monkeypatch):
        """A bad value should be skipped with a warning, not crash."""
        path = _write_yaml(tmp_path, _MINIMAL_YAML)
        monkeypatch.setenv("MESHTASTIC__CHANNEL", "not_a_number")
        from main import load_config
        cfg = load_config(path)
        assert cfg["channel"] == 1  # YAML value unchanged

    def test_env_creates_missing_section(self, tmp_path, monkeypatch):
        """Env var for a key not in YAML should create the nested dict."""
        yaml_content = "channel: 1\nconnection:\n  type: serial\n"
        path = _write_yaml(tmp_path, yaml_content)
        monkeypatch.setenv("MESHTASTIC__ADMIN__PASSWORD", "fromenv")
        from main import load_config
        cfg = load_config(path)
        assert cfg["admin"]["password"] == "fromenv"
