# 项目架构规范

## 定位

`mcp-memory` 是 memory engine 项目，不是传统 CRUD 后台。代码组织必须围绕记忆生命周期设计：

```text
capture -> normalize -> store L0 -> extract L1 -> consolidate L2 -> update L3 -> recall
```

## 包名

- Python 包目录必须使用 `src/mcp_memory/`。
- 禁止使用 `src/mcp-memory/` 作为可导入包名。
- 所有本地导入统一从 `mcp_memory` 开始。

## 分层职责

| 层级 | 目录 | 职责 |
|------|------|------|
| ORM | `models/` | 表结构映射，不写业务逻辑 |
| DTO | `schemas/` | 输入输出结构、内部任务 payload |
| Repository | `repositories/` | PGSQL 查询和写入，不做 LLM 调用和业务决策 |
| Service | `services/` | 单个用例，如 capture、recall、upsert switch |
| Pipeline | `pipelines/` | 可重试的多步骤记忆处理流程 |
| Retrieval | `retrieval/` | 向量检索、过滤、排序、上下文拼装 |
| Adapter | `mcp/`, `api/`, `workers/`, `cli/` | 协议入口，只做参数转换和调用 service |

## 调用方向

允许：

```text
adapter -> service -> repository -> models
pipeline -> service/repository
retrieval -> repository
```

禁止：

- `models/` 导入 service、repository、adapter。
- repository 调用 LLM、MCP、HTTP handler。
- adapter 直接拼 SQL 或直接操作 ORM 对象完成业务流程。
- pipeline 依赖具体 HTTP 或 MCP 请求对象。

## 文件规模

- 普通 Python 文件建议不超过 300 行。
- 字段密集型 ORM 文件可放宽到 400 行。
- 单个目录超过 8 个文件时，应按领域拆子目录。

## 命名

- repository 文件使用领域名：`memory_items.py`, `switch.py`。
- pipeline 文件使用方向名：`l0_to_l1.py`, `l1_to_l2.py`, `l2_to_l3.py`。
- service 文件使用用例名：`capture.py`, `recall.py`, `memory_switch.py`。
