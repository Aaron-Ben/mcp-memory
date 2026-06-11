# MCP Memory 项目规范

本项目是以 PostgreSQL 为主存储的分层记忆系统。核心目标是稳定记录、抽取、聚合和召回 L0/L1/L2/L3 记忆，而不是先假定为传统 Web 业务后台。

## 核心原则

1. **核心优先于协议**：memory engine、PGSQL repository、pipeline 是核心；HTTP、MCP、CLI、worker 都只是适配层。
2. **分层记忆边界清晰**：L0 保存原始事实来源，L1 保存原子事实，L2 保存场景聚合，L3 保存长期画像。
3. **存储模型可审计**：所有派生记忆必须保留来源、置信度和更新时间，避免不可解释的覆盖。
4. **幂等优先**：采集、抽取、聚合、召回都必须考虑重复执行和失败重试。
5. **规则服从项目现实**：不要套用外部项目的 `app/core`、REST-only 或 Router-only 结构。

## 推荐项目结构

```text
src/mcp_memory/
├── __init__.py
├── models/              # SQLAlchemy ORM
├── schemas/             # Pydantic DTO 和响应模型
├── enums/               # MemoryLayer, MemoryStatus, MemoryType 等
├── repositories/        # PGSQL 读写，禁止承载业务决策
├── services/            # capture, extract, consolidate, recall
├── pipelines/           # L0->L1, L1->L2, L2->L3 后台任务
├── retrieval/           # 向量检索、过滤、rerank、上下文组装
├── db/                  # engine、session、迁移入口
├── mcp/                 # MCP tools/resources 适配层
├── api/                 # 可选 HTTP 适配层
├── workers/             # 后台任务入口
└── utils/
```

> 当前若存在 `src/mcp-memory/`，应迁移为 `src/mcp_memory/`。Python 包目录不应使用连字符。

## 规则文件索引

| 文件 | 职责 |
|------|------|
| [project-architecture.md](rules/project-architecture.md) | 项目结构、模块边界、调用方向 |
| [memory-layers.md](rules/memory-layers.md) | L0/L1/L2/L3 职责、来源、更新规则 |
| [pgsql-storage.md](rules/pgsql-storage.md) | PGSQL、JSONB、pgvector、幂等键、索引规范 |
| [pipeline-and-transactions.md](rules/pipeline-and-transactions.md) | pipeline、批处理、事务边界、重试规范 |
| [api-and-mcp-boundary.md](rules/api-and-mcp-boundary.md) | MCP/HTTP/CLI 适配层边界 |
| [testing.md](rules/testing.md) | 单元、集成、迁移、pipeline 测试要求 |
| [observability.md](rules/observability.md) | 日志、指标、trace、审计字段 |
| [code-style.md](rules/code-style.md) | 代码风格、类型注解、导入和文件规模 |
| [database.md](rules/database.md) | 通用数据库模型和迁移规则 |
| [transaction.md](rules/transaction.md) | 通用事务规则 |
| [async-programming.md](rules/async-programming.md) | 异步代码和阻塞 I/O 规则 |
| [error-handling.md](rules/error-handling.md) | 分层错误处理 |
| [enums.md](rules/enums.md) | 枚举定义和导出 |
| [comments.md](rules/comments.md) | 注释和 docstring |
| [protobuf.md](rules/protobuf.md) | 可选 gRPC/Protobuf 生成规则 |

## 执行要求

- 写代码前先确认规则是否适用于当前层级：核心层、存储层、pipeline 层、协议适配层的要求不同。
- 一旦发现规则与项目目标冲突，应优先修正规则，再继续扩展代码。
- 新增模型、repository、pipeline、MCP tool 时，必须同步检查对应规则是否覆盖该模块。
