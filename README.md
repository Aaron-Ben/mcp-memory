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