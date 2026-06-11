import asyncio

from mcp_memory.grpc import serve

__all__ = ["run"]


def run() -> None:
    asyncio.run(serve())
