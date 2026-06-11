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

# docket启动
docker compose -f docker-compose-db.yaml up -d

# 迁移建表
alembic upgrade head

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件配置数据库和服务

```

## 项目结构

```text
mcp-memory/
├── main.py                         # 项目启动入口，仅负责调用 mcp_memory.app.run()
├── pyproject.toml                  # Python 依赖、开发依赖、ruff/mypy 配置
├── docker-compose-db.yaml          # 本地 PostgreSQL/pgvector 数据库
├── alembic.ini                     # Alembic 配置
├── migrations/                     # 数据库迁移脚本
│   ├── env.py                      # Alembic 迁移环境
│   └── versions/                   # 具体迁移版本
└── src/mcp_memory/
    ├── app.py                      # 应用启动编排，目前启动 gRPC 服务
    ├── config.py                   # 环境变量与配置项
    ├── db/                         # 数据库连接、Session、健康检查
    ├── models/                     # SQLAlchemy 表模型
    │   ├── base.py                 # Base、时间字段、软删除公共字段
    │   ├── memory_items.py         # memory_items 记忆表
    │   └── switch.py               # memory_switch 开关表
    ├── schemas/                    # Pydantic 入参/数据传输结构
    ├── repositories/               # 数据库读写层，封装 SQL/ORM 持久化操作
    ├── services/                   # 业务逻辑层，如 L0 保存、过滤、metadata 构造
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
  -> PostgreSQL memory_items
```

分层职责：

- `models`: 定义数据库表结构。
- `schemas`: 定义服务内部入参和数据传输结构，不直接访问数据库。
- `repositories`: 只处理数据库读写，避免混入业务规则。
- `services`: 处理业务规则和流程编排，例如 L0 消息过滤、`memory_id` 生成、metadata 构造。
- `grpc`: 对外提供 gRPC 接口，负责协议转换和调用 service。
- `proto`: 保存协议定义及生成代码。修改 `memory.proto` 后需要重新生成 `*_pb2*` 文件。

重新生成 Protobuf 代码：

```bash
python -m grpc_tools.protoc \
  -I src \
  --python_out=src \
  --grpc_python_out=src \
  --pyi_out=src \
  src/mcp_memory/proto/memory.proto
```
