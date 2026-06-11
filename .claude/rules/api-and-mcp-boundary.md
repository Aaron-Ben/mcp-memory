# API 与 MCP 边界规范

## 核心原则

MCP、HTTP、CLI、worker 都是适配层。适配层只负责协议转换，不负责核心记忆逻辑。

## MCP 适配层

MCP tools/resources 应：

- 校验输入。
- 调用 service。
- 返回稳定、简洁、可序列化的结果。
- 不直接拼 SQL。
- 不直接操作 ORM 对象完成业务流程。

MCP tools/resources 不应：

- 调用 repository 绕过 service。
- 在 tool 中执行 L0->L3 的完整复杂流程，除非封装为 service/pipeline。
- 暴露内部数据库字段作为外部协议契约。

## HTTP API 适配层

如果提供 HTTP API：

- 可以使用 REST，但不强制所有能力都 RESTful。
- Router 只做 request/response 转换。
- Router 调用 service，不直接调用 repository。
- 错误响应格式应统一。

## CLI 与 worker

CLI 和 worker 可以直接调用 service 或 pipeline runner。

禁止：

- CLI 复制 service 里的业务逻辑。
- worker 直接散落 SQL 和 LLM 处理逻辑。

## DTO 边界

- 外部请求 DTO 与内部 pipeline DTO 分开。
- 不把 ORM 模型直接返回给外部协议。
- 内部 schema 可以更贴近表结构，外部 schema 必须稳定且少暴露实现细节。
