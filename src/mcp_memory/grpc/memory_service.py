from __future__ import annotations

import time
from typing import Any

import grpc

from mcp_memory.db import async_db_session
from mcp_memory.proto import memory_pb2, memory_pb2_grpc
from mcp_memory.schemas import L0MessageCreate
from mcp_memory.services import l0_memory_service

__all__ = ["MemoryService"]


class MemoryService(memory_pb2_grpc.MemoryServicer):
    """gRPC Memory service implementation.

    当前阶段只实现 L0 原始消息保存。其它 RPC 先返回兼容默认值,
    避免 mcp-client 调用时因为 UNIMPLEMENTED 直接报错。
    """

    async def IngestMessages(
        self,
        request: memory_pb2.IngestRequest,
        context: grpc.aio.ServicerContext,
    ) -> memory_pb2.IngestReply:
        user_id = request.user_id.strip()
        conversation_id = request.conversation_id.strip()
        if not user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")
        if not conversation_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "conversation_id is required")
        if len(request.messages) == 0:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "messages are required")

        source_session_key = self._build_session_key(user_id, conversation_id)
        async with async_db_session() as db:
            for index, message in enumerate(request.messages):
                normalized = self._normalize_message(message, index)
                if not normalized["content"] and normalized["role"] != "assistant":
                    continue
                await l0_memory_service.save_message(
                    db,
                    obj_in=L0MessageCreate(
                        user_id=user_id,
                        source_conversation_id=conversation_id,
                        source_session_key=source_session_key,
                        role=normalized["role"],
                        content=normalized["content"],
                        message_id=normalized["message_id"],
                        timestamp_ms=normalized["timestamp_ms"],
                        metadata=normalized["metadata"],
                    ),
                )

        return memory_pb2.IngestReply(accepted=True)

    async def GetMemory(
        self,
        request: memory_pb2.GetMemoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> memory_pb2.GetMemoryReply:
        return memory_pb2.GetMemoryReply(memory_text="")

    async def Enabled(
        self,
        request: memory_pb2.EnabledRequest,
        context: grpc.aio.ServicerContext,
    ) -> memory_pb2.EnabledReply:
        return memory_pb2.EnabledReply(enabled=True)

    async def Dream(
        self,
        request: memory_pb2.DreamRequest,
        context: grpc.aio.ServicerContext,
    ) -> memory_pb2.DreamReply:
        return memory_pb2.DreamReply(enabled=False)

    async def ResetMemory(
        self,
        request: memory_pb2.ResetRequest,
        context: grpc.aio.ServicerContext,
    ) -> memory_pb2.ResetReply:
        return memory_pb2.ResetReply(success=False)

    def _normalize_message(self, message: memory_pb2.Message, index: int) -> dict[str, Any]:
        role = self._normalize_role(message.role)
        content = (message.content or "").strip()
        timestamp_ms = int(message.timestamp) if int(message.timestamp) > 0 else int(time.time() * 1000)
        message_id = (message.id or "").strip() or f"grpc_msg_{timestamp_ms}_{index}"
        tool_name = (message.tool_name or "").strip()
        metadata: dict[str, Any] = {}
        if tool_name:
            metadata["tool_name"] = tool_name
        return {
            "message_id": message_id,
            "role": role,
            "content": content,
            "timestamp_ms": timestamp_ms,
            "metadata": metadata,
        }

    def _normalize_role(self, role: str) -> str:
        normalized = (role or "").strip().lower()
        if normalized in {"user", "assistant", "tool"}:
            return normalized
        if normalized in {"tool_result", "tool-result", "toolresult"}:
            return "tool"
        return "assistant"

    def _build_session_key(self, user_id: str, conversation_id: str) -> str:
        return f"grpc:{self._sanitize_key(user_id)}:{self._sanitize_key(conversation_id)}"

    def _sanitize_key(self, value: str) -> str:
        return "".join(char if char.isalnum() or char in "_.:-" else "_" for char in value)
