"""
Structured logging configuration for MeshtasticBot.

Call configure_logging() once at startup (in main.py).

Output format is auto-detected:
- TTY (development): coloured human-readable output via _PrettyConsoleRenderer
- Non-TTY (Docker / prod): JSON lines via JSONRenderer

All stdlib loggers (Flask, Meshtastic SDK, etc.) are routed through the
same structlog pipeline so every log line comes out in a consistent format.

Usage in any module:
    import structlog
    log = structlog.get_logger()
    log.info("event_name", key=value)
"""

import logging
import sys

import structlog

# ---------------------------------------------------------------------------
# ANSI colour codes (same values as colorama — no extra dependency needed)
# ---------------------------------------------------------------------------
_R   = "\033[0m"    # reset
_DIM = "\033[2m"    # dim / grey
_B   = "\033[1m"    # bold

_LEVEL_COLORS: dict[str, str] = {
    "debug":    "\033[96m",   # bright cyan
    "info":     "\033[92m",   # bright green
    "warning":  "\033[93m",   # bright yellow
    "error":    "\033[91m",   # bright red
    "critical": "\033[1;91m", # bold bright red
}
_KEY_COLOR = "\033[36m"   # cyan
_VAL_COLOR = "\033[93m"   # bright yellow
_MOD_COLOR = "\033[2;36m" # dim cyan


class _PrettyConsoleRenderer:
    """
    Human-readable console renderer for TTY sessions.

    Format:
        18:00:09 [INFO    ] commands  event_name            key=value  key2=value2
    """

    def __call__(self, _logger: object, _method: str, event_dict: dict) -> str:
        ts     = event_dict.pop("timestamp", "")
        level  = event_dict.pop("level", _method) or ""
        event  = str(event_dict.pop("event", ""))
        module = event_dict.pop("_logger", None) or event_dict.pop("logger_name", None)
        # Drop internal structlog/stdlib housekeeping fields
        event_dict.pop("_record", None)
        event_dict.pop("_from_structlog", None)

        lvl_color = _LEVEL_COLORS.get(level.lower(), "")
        parts: list[str] = []

        if ts:
            parts.append(f"{_DIM}{ts}{_R}")

        level_label = level.upper().ljust(8)
        parts.append(f"{lvl_color}[{level_label}]{_R}")

        if module:
            parts.append(f"{_MOD_COLOR}{module:<12}{_R}")

        parts.append(f"{_B}{event:<32}{_R}")

        for k, v in event_dict.items():
            parts.append(f"{_KEY_COLOR}{k}{_R}={_VAL_COLOR}{v!r}{_R}")

        return "  ".join(parts)


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib root logger.  Call once before any logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    is_tty = sys.stderr.isatty()

    # Short HH:MM:SS timestamp for human eyes; ISO-8601 for log aggregators
    ts_format = "%H:%M:%S" if is_tty else "iso"

    # Processors that run on every log record (both structlog and stdlib)
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt=ts_format),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = _PrettyConsoleRenderer() if is_tty else structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Remove any handlers already attached (e.g. basicConfig defaults)
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)
