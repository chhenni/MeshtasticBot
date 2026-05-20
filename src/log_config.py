"""
Structured logging configuration for MeshtasticBot.

Call configure_logging() once at startup (in main.py).

Output format is auto-detected:
- TTY (development): coloured human-readable output via ConsoleRenderer
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


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib root logger.  Call once before any logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Processors that run on every log record (both structlog and stdlib)
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if sys.stderr.isatty():
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

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
