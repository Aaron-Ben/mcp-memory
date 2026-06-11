from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Message(_message.Message):
    __slots__ = ("id", "role", "content", "tool_name", "timestamp")
    ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    TOOL_NAME_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    id: str
    role: str
    content: str
    tool_name: str
    timestamp: int
    def __init__(self, id: _Optional[str] = ..., role: _Optional[str] = ..., content: _Optional[str] = ..., tool_name: _Optional[str] = ..., timestamp: _Optional[int] = ...) -> None: ...

class IngestRequest(_message.Message):
    __slots__ = ("user_id", "conversation_id", "messages")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    CONVERSATION_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    conversation_id: str
    messages: _containers.RepeatedCompositeFieldContainer[Message]
    def __init__(self, user_id: _Optional[str] = ..., conversation_id: _Optional[str] = ..., messages: _Optional[_Iterable[_Union[Message, _Mapping]]] = ...) -> None: ...

class IngestReply(_message.Message):
    __slots__ = ("accepted",)
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    def __init__(self, accepted: _Optional[bool] = ...) -> None: ...

class GetMemoryRequest(_message.Message):
    __slots__ = ("user_id", "query", "limit")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    query: str
    limit: int
    def __init__(self, user_id: _Optional[str] = ..., query: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class GetMemoryReply(_message.Message):
    __slots__ = ("memory_text",)
    MEMORY_TEXT_FIELD_NUMBER: _ClassVar[int]
    memory_text: str
    def __init__(self, memory_text: _Optional[str] = ...) -> None: ...

class EnabledRequest(_message.Message):
    __slots__ = ("user_id", "enabled")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    enabled: bool
    def __init__(self, user_id: _Optional[str] = ..., enabled: _Optional[bool] = ...) -> None: ...

class EnabledReply(_message.Message):
    __slots__ = ("enabled",)
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    def __init__(self, enabled: _Optional[bool] = ...) -> None: ...

class DreamRequest(_message.Message):
    __slots__ = ("user_id", "enabled")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    enabled: bool
    def __init__(self, user_id: _Optional[str] = ..., enabled: _Optional[bool] = ...) -> None: ...

class DreamReply(_message.Message):
    __slots__ = ("enabled",)
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    def __init__(self, enabled: _Optional[bool] = ...) -> None: ...

class ResetRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    def __init__(self, user_id: _Optional[str] = ...) -> None: ...

class ResetReply(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: _Optional[bool] = ...) -> None: ...
