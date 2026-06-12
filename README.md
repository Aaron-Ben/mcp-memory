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
# memory.l1.dedup=true 启用 L1 去重，false 关闭 L1 去重

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
    │   ├── pipeline_state.py       # L0->L1/L1->L2 调度状态表
    │   └── switch.py               # memory_switch 开关表
    ├── pipelines/                  # 记忆分层流水线实现，负责一次具体 L0->L1 / L1->L2 / L2->L3 执行
    │   ├── l0_to_l1.py             # 查询增量 L0、质量过滤、LLM 抽取、dedup、写入 L1
    │   ├── l1_to_l2.py             # 查询增量 L1、生成/合并 L2 场景块、写入 L2
    │   └── l2_to_l3.py             # 查询变化 L2、生成/更新 L3 用户画像
    ├── extractors/                 # LLM 抽取器与响应解析
    │   └── l1_extractor.py         # L1 prompt 调用、JSON 解析和解析诊断日志
    ├── schemas/                    # Pydantic 入参/数据传输结构
    ├── repositories/               # 数据库读写层，封装 SQL/ORM 持久化操作
    │   ├── memory_items.py         # memory_items 的 L0/L1/L2 查询、写入、归档、向量召回
    │   └── pipeline_state.py       # pipeline_state 的计数、cursor、运行状态和 timer 状态更新
    ├── services/                   # 业务服务层，封装领域规则和跨模块编排
    │   ├── l0_memory.py            # L0 原始消息保存、system-reminder 过滤、L0 memory_id 生成
    │   ├── l1_memory.py            # L1 记忆保存、embedding 生成、L1 memory_id 和 metadata 构造
    │   ├── l1_dedup.py             # L1 相似召回后的 LLM dedup 决策，输出 store/update/merge/skip
    │   ├── l2_scene.py             # L2 场景选择、scene markdown 生成、filename/memory_id/meta 构造
    │   ├── l3_persona.py           # L3 persona markdown 生成、Scene Navigation 追加、L3 memory_id/meta 构造
    │   └── pipeline_scheduler.py   # 进程内调度器，连接 gRPC 入站通知、pipeline_state、L0->L1、L1->L2 和 L2->L3
    ├── prompts/                    # Markdown 提示词与 PromptLoader
    │   └── modules/                # 功能模块提示词，如 L1 抽取、L2 场景 prompt
    ├── adapters/                   # 外部能力适配，如 LLM runner 和 embedding provider
    ├── utils/                      # 通用工具，如 L1 文本质量过滤
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
  -> L2 timer
  -> mcp_memory.pipelines.l1_to_l2.L1ToL2Pipeline
  -> PostgreSQL memory_items(layer = 2)
  -> mcp_memory.pipelines.l2_to_l3.L2ToL3Pipeline
  -> PostgreSQL memory_items(layer = 3)
```

分层职责：

- `models`: 定义数据库表结构。
- `schemas`: 定义服务内部入参和数据传输结构，不直接访问数据库。
- `repositories`: 只处理数据库读写，避免混入业务规则。
- `services`: 处理业务规则和流程编排，例如 L0 消息过滤、`memory_id` 生成、metadata 构造、L1 dedup、L2 场景构造和后台调度。`services` 不应该直接承担大段 SQL，也不应该把一次完整分层转换的执行细节写散。
- `pipeline_scheduler.py`: 当前是进程内调度器，不是 CRUD，也不是 LLM pipeline 本体。它负责接收 `IngestMessages` 后的 L0 通知，维护每个 `(user_id, source_session_key)` 的调度任务，按照 warmup/轮数阈值或 idle timer 触发 L0->L1；当 L1 实际写入新记忆后，再根据 `pipeline_state` 中的 L2 调度字段设置 L1->L2 延迟 timer；当 L2 实际写入场景后，按 `user_id` 触发 L2->L3，并用内存 task/pending 避免同一用户并发生成 persona；同时负责后台 task 的创建、取消、异常落库和 shutdown 清理。
- `pipelines`: 执行一次具体跨层转换，例如从 L0 查询增量消息、调用 LLM 抽取 L1、把 L1 整合为 L2、推进 cursor。pipeline 本身不决定“什么时候运行”，运行时机由 `pipeline_scheduler.py` 和 `pipeline_state` 决定。
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
  -> embedding 召回相似 L1
  -> LLM dedup 决策 store/update/merge/skip
  -> 写入 memory_items(layer = 1)，必要时归档旧 L1
  -> 更新 pipeline_state.last_l1_cursor / last_scene_name
```

调度状态保存在 `pipeline_state` 表中。首次建库或更新后需要执行：

```bash
alembic upgrade head
```

当前 L1 去重已实现向量召回 + LLM 决策的基础路径：`store` 直接写入，`skip` 忽略新记忆，`update` / `merge` 会先归档命中的旧 L1，再写入新的 L1。尚未补齐 `yuanxi-memory` 中可能使用的全文检索 fallback、多阶段召回优化和更细粒度冲突策略。

可以通过 `config/local.yaml` 控制是否启用 L1 去重：

```yaml
memory:
  l1:
    dedup: true
```

设置为 `false` 时，L0->L1 会跳过相似 L1 召回和 LLM dedup，抽取出的 L1 直接写入。

重新生成 Protobuf 代码：

```bash
python -m grpc_tools.protoc \
  -I src \
  --python_out=src \
  --grpc_python_out=src \
  --pyi_out=src \
  src/mcp_memory/proto/memory.proto
```
