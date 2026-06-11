## 🚀 快速开始

### 环境要求

- Python 3.13+
- PostgreSQL 15+

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd mcp-memory

# 创建环境，推荐conda
conda create --name mcp-memory python=3.13

# 切换环境
conda activate mcp-memory

# 安装依赖
python -m pip install -e ".[dev]"

# 配置本地服务
cp config/local.example.yaml config/local.yaml
# 编辑 config/local.yaml 配置数据库、gRPC、LLM 和 embedding

# docket启动
docker compose -f docker-compose-db.yaml up -d

# 迁移建表
alembic upgrade head

```

## 项目结构

```text
mcp-memory/
├── main.py                         # 项目启动入口，仅负责调用 mcp_memory.app.run()
├── pyproject.toml                  # Python 依赖、开发依赖、ruff/mypy 配置
├── docker-compose-db.yaml          # 本地 PostgreSQL/pgvector 数据库
├── alembic.ini                     # Alembic 配置
├── config/
│   ├── local.example.yaml          # 本地配置模板
│   └── local.yaml                  # 本地私有配置，包含数据库、gRPC、LLM、embedding 等配置
├── migrations/                     # 数据库迁移脚本
│   ├── env.py                      # Alembic 迁移环境
│   └── versions/                   # 具体迁移版本
└── src/mcp_memory/
    ├── app.py                      # 应用启动编排，目前启动 gRPC 服务
    ├── config.py                   # 读取 config/local.yaml 并生成运行配置
    ├── db/                         # 数据库连接、Session、健康检查
    ├── models/                     # SQLAlchemy 表模型
    │   ├── base.py                 # Base、时间字段、软删除公共字段
    │   ├── memory_items.py         # memory_items 记忆表
    │   ├── pipeline_state.py       # L0->L1 调度状态表
    │   └── switch.py               # memory_switch 开关表
    ├── pipelines/                  # 后台记忆分层流水线，如 L0->L1
    ├── schemas/                    # Pydantic 入参/数据传输结构
    ├── repositories/               # 数据库读写层，封装 SQL/ORM 持久化操作
    ├── services/                   # 业务逻辑层，如 L0 保存、L1 写入、pipeline 调度
    ├── prompts/                    # Markdown 提示词与 PromptLoader
    │   └── modules/                # 功能模块提示词，如 L1 抽取 prompt
    ├── grpc/                       # gRPC 服务端实现
    │   ├── server.py               # gRPC server 启动与端口监听
    │   └── memory_service.py       # Memory service RPC 实现
    └── proto/                      # Protobuf 协议与生成代码
        ├── memory.proto            # gRPC 协议定义，需与 mcp-client 保持兼容
        ├── memory_pb2.py           # 由 grpc_tools 自动生成，不手动修改
        ├── memory_pb2_grpc.py      # 由 grpc_tools 自动生成，不手动修改
        └── memory_pb2.pyi          # 由 grpc_tools 自动生成的类型提示
```

当前主要调用链：

```text
mcp-client
  -> gRPC IngestMessages
  -> mcp_memory.grpc.memory_service.MemoryService
  -> mcp_memory.services.l0_memory.L0MemoryService
  -> mcp_memory.repositories.memory_items.MemoryItemRepository
  -> PostgreSQL memory_items(layer = 0)
  -> mcp_memory.services.pipeline_scheduler.PipelineScheduler
  -> PostgreSQL pipeline_state
  -> mcp_memory.pipelines.l0_to_l1.L0ToL1Pipeline
  -> PostgreSQL memory_items(layer = 1)
```

分层职责：

- `models`: 定义数据库表结构。
- `schemas`: 定义服务内部入参和数据传输结构，不直接访问数据库。
- `repositories`: 只处理数据库读写，避免混入业务规则。
- `services`: 处理业务规则和流程编排，例如 L0 消息过滤、`memory_id` 生成、metadata 构造、L1 后台调度。
- `pipelines`: 执行跨层流水线，例如从 L0 查询增量消息、调用 LLM 抽取 L1、推进 cursor。
- `grpc`: 对外提供 gRPC 接口，负责协议转换和调用 service。
- `proto`: 保存协议定义及生成代码。修改 `memory.proto` 后需要重新生成 `*_pb2*` 文件。

## L0 到 L1

当前已实现最小自动触发闭环：

```text
IngestMessages
  -> 保存 L0
  -> PipelineScheduler.notify_conversation
  -> 达到 warmup/阈值则后台触发 L1
  -> 未达到阈值则设置 idle timer
  -> L0ToL1Pipeline 按 last_l1_cursor 查询 L0
  -> LLM 抽取 L1
  -> 写入 memory_items(layer = 1)
  -> 更新 pipeline_state.last_l1_cursor / last_scene_name
```

调度状态保存在 `pipeline_state` 表中。首次建库或更新后需要执行：

```bash
alembic upgrade head
```

当前仍未实现完整 `yuanxi-memory` 的 L1 去重与合并：相似 L1 召回、LLM dedup、`update/merge/skip`、旧 L1 归档等逻辑后续补充。

重新生成 Protobuf 代码：

```bash
python -m grpc_tools.protoc \
  -I src \
  --python_out=src \
  --grpc_python_out=src \
  --pyi_out=src \
  src/mcp_memory/proto/memory.proto
```
