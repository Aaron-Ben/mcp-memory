# 枚举类型规范

## 存放位置

| 类型 | 位置 | 说明 |
|------|------|------|
| **业务枚举** | `src/mcp_memory/enums/` | 记忆层级、状态、类型等业务枚举 |
| **服务层内部枚举** | 对应 services 目录 | 仅供服务层内部使用的枚举可保留原位置 |

## 目录结构

```
src/mcp_memory/enums/
├── __init__.py          # 统一导出，定义 __all__
├── memory.py            # MemoryLayer, MemoryStatus, MemoryType
├── pipeline.py          # PipelineStatus, PipelineStep
└── retrieval.py         # RetrievalMode
```

## 命名规范

| 类型 | 规范 | 正确示例 | 错误示例 |
|------|------|----------|----------|
| **枚举类名** | PascalCase，**不带 `Enum` 后缀** | `MemoryLayer`, `MemoryStatus` | `MemoryLayerEnum`, `memory_status` |
| **枚举值名** | UPPER_SNAKE_CASE | `L0`, `ACTIVE`, `ARCHIVED` | `active`, `Pending` |
| **文件名** | 小写下划线，按业务领域 | `memory.py`, `pipeline.py` | `Memory.py`, `memoryEnum.py` |

## 定义方式

**必须使用 `str, Enum` 组合**：

```python
from enum import Enum


class MemoryStatus(str, Enum):
    """记忆状态"""

    ACTIVE = "active"      # 可召回
    ARCHIVED = "archived"  # 已归档
```

### 好处

- 可直接用于字符串操作（JSON 序列化、字符串拼接、Redis key）
- 类型安全，IDE 自动补全
- Pydantic 自动解析字符串为枚举
- API 请求/响应无需转换

### 禁止的定义方式

```python
# ❌ 错误：纯 Enum（无法直接序列化为字符串）
class MemoryStatus(Enum):
    ACTIVE = "active"

# ❌ 错误：使用 Literal 替代枚举
MemoryStatusType = Literal["active", "archived"]

# ❌ 错误：带 Enum 后缀
class MemoryStatusEnum(str, Enum):
    ACTIVE = "active"
```

## 文档规范

每个枚举类**必须**有文档字符串，枚举值**建议**添加行内注释：

```python
class MemoryLayer(str, Enum):
    """记忆层级"""

    L0 = "0"  # 原始消息
    L1 = "1"  # 原子事实
    L2 = "2"  # 场景记忆
    L3 = "3"  # 长期画像
```

## 导出规范

`__init__.py` 必须统一导出所有枚举，并定义 `__all__`：

```python
from .memory import MemoryLayer, MemoryStatus, MemoryType
from .pipeline import PipelineStatus, PipelineStep

__all__ = [
    "MemoryLayer",
    "MemoryStatus",
    "MemoryType",
    "PipelineStatus",
    "PipelineStep",
]
```

## 使用规范

### 导入方式

```python
# ✅ 推荐：从 enums 包直接导入
from mcp_memory.enums import MemoryLayer, MemoryStatus

# ✅ 允许：导入整个模块
from mcp_memory import enums
status = enums.MemoryStatus.ACTIVE

# ❌ 禁止：从子模块导入（除非在 enums 包内部）
from mcp_memory.enums.memory import MemoryStatus
```

### 比较和使用

由于枚举继承了 `str`，可以直接当作字符串使用，**禁止使用 `.value`**：

```python
# ✅ 正确：直接比较（枚举继承 str，可以和字符串比较）
if item.status == MemoryStatus.ACTIVE:
    ...

if layer == MemoryLayer.L1:  # 可以和数据库/Redis 返回的字符串直接比较
    ...

# ✅ 正确：用于字符串拼接（因为继承了 str）
key = f"memory:{MemoryStatus.ACTIVE}:{memory_id}"

# ✅ 正确：用于日志输出（自动转为字符串）
logger.info(f"当前状态: {status}")

# ✅ 正确：用于 Pydantic 模型
class MemoryCreate(BaseModel):
    status: MemoryStatus = MemoryStatus.ACTIVE

# ✅ 正确：用于集合定义
TERMINAL_STATUSES = {MemoryStatus.ARCHIVED}

# ❌ 错误：使用 .value 进行比较（多此一举）
if item.status == MemoryStatus.ACTIVE.value:
    ...

# ❌ 错误：使用 .value 获取字符串值（直接使用枚举即可）
status_str = MemoryStatus.ACTIVE.value  # 应该直接用 MemoryStatus.ACTIVE
```

## 新增枚举流程

1. 在 `src/mcp_memory/enums/` 下对应文件中添加枚举类
2. 在 `__init__.py` 中导出
3. 更新 `__all__` 列表

## 违规模式检测

发现以下情况应立即指出并给出修复建议：

- 枚举类定义在 `src/mcp_memory/enums/` 以外的位置（服务层内部枚举除外）
- 枚举类名带有 `Enum` 后缀
- 使用纯 `Enum` 而非 `str, Enum`
- 使用 `Literal` 替代枚举
- 枚举值命名不符合 UPPER_SNAKE_CASE
- 枚举类缺少文档字符串
- 从子模块直接导入枚举（应从 `mcp_memory.enums` 导入）
- **使用 `.value` 获取枚举值**（`str, Enum` 可直接当字符串使用）
