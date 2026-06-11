from __future__ import annotations

import asyncio
import signal

import grpc

from mcp_memory.config import settings
from mcp_memory.db import check_db_health
from mcp_memory.grpc.memory_service import MemoryService
from mcp_memory.proto import memory_pb2_grpc
from mcp_memory.services import pipeline_scheduler

__all__ = ["serve"]


async def serve() -> None:
    healthy = await check_db_health()
    if not healthy:
        raise RuntimeError("数据库健康检查失败")

    server = grpc.aio.server()
    memory_pb2_grpc.add_MemoryServicer_to_server(MemoryService(), server)
    listen_addr = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
    bound_port = server.add_insecure_port(listen_addr)
    if bound_port == 0:
        raise RuntimeError(f"gRPC 端口绑定失败: {listen_addr}")
    await server.start()
    print(f"mcp-memory gRPC started: {listen_addr}")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    finally:
        await pipeline_scheduler.shutdown()
        await server.stop(grace=5)
        print("mcp-memory gRPC stopped")
