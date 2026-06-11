import asyncio
import logging
import sys

from mcp_memory.grpc import serve

__all__ = ["run"]


class ColorFormatter(logging.Formatter):
    """ANSI color formatter for terminal logs."""

    COLORS = {
        logging.DEBUG: "\033[90m",
        logging.INFO: "\033[36m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[41m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not sys.stderr.isatty():
            return message
        color = self.COLORS.get(record.levelno)
        if color is None:
            return message
        return f"{color}{message}{self.RESET}"


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        ColorFormatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    )
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def run() -> None:
    configure_logging()
    asyncio.run(serve())
