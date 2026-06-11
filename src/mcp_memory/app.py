import asyncio
import logging

from mcp_memory.grpc import serve

__all__ = ["run"]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def run() -> None:
    configure_logging()
    asyncio.run(serve())
