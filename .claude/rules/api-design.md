# 接口设计规范

本文件保留为兼容入口。新代码应优先遵守 [api-and-mcp-boundary.md](api-and-mcp-boundary.md)。

## 基本原则

- 本项目不强制 REST-only。
- HTTP API、MCP tools、CLI、worker 都是适配层。
- 适配层只做协议转换、认证鉴权、输入输出校验。
- 核心逻辑必须下沉到 service、pipeline、repository。

## HTTP API

如果实现 HTTP API：

- 路由命名使用小写加下划线。
- Router 不直接操作 ORM。
- Router 不直接拼 SQL。
- Router 不执行 L0->L3 的复杂流程，只调用 service 或 pipeline runner。

## MCP API

MCP tools/resources 是本项目的重点协议入口之一。

- Tool 输入必须使用 schema 校验。
- Tool 输出必须稳定、简洁、可序列化。
- Tool 不直接暴露内部 ORM 对象。
- Tool 不绕过 service 调 repository。

## Repository 入参

Repository 层应使用明确 schema 或具名参数。

禁止：

- `**kwargs` 承载写入字段。
- 无约束的 `dict[str, Any]` 作为主要写入模型。
- 在 repository 内做协议层响应模型转换。

## 违规模式检测

- 适配层直接拼 SQL。
- MCP/HTTP handler 直接操作 ORM 完成业务流程。
- Repository 调用 LLM 或外部协议。
- 外部响应直接返回 ORM 模型。
