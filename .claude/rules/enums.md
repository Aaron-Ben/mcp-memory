# 枚举类型规范

## 存放位置

| 类型 | 位置 | 说明 |
|------|------|------|
| **业务枚举** | `app/core/enums/` | 用户、订单、余额等业务相关枚举 |
| **服务层内部枚举** | 对应 services 目录 | 仅供服务层内部使用的枚举可保留原位置 |

## 目录结构

```
app/core/enums/
├── __init__.py          # 统一导出，定义 __all__
├── user.py              # 用户相关：Gender, UserStatus
├── balance.py           # 余额相关：BalanceType, TransactionType
├── order.py             # 订单相关：OrderStatus, PaymentMethod
├── redemption.py        # 兑换码相关：RedemptionCodeStatus
├── email.py             # 邮箱相关：EmailPurpose
└── task.py              # 任务相关：TaskStatus, TaskFinalStatus
```

## 命名规范

| 类型 | 规范 | 正确示例 | 错误示例 |
|------|------|----------|----------|
| **枚举类名** | PascalCase，**不带 `Enum` 后缀** | `Gender`, `OrderStatus` | `GenderEnum`, `order_status` |
| **枚举值名** | UPPER_SNAKE_CASE | `MALE`, `PENDING`, `BIND_EMAIL` | `male`, `Pending` |
| **文件名** | 小写下划线，按业务领域 | `user.py`, `order.py` | `User.py`, `orderEnum.py` |

## 定义方式

**必须使用 `str, Enum` 组合**：

```python
from enum import Enum


class Gender(str, Enum):
    """性别"""

    MALE = "M"      # 男
    FEMALE = "F"    # 女
    OTHER = "O"     # 其他
```

### 好处

- 可直接用于字符串操作（JSON 序列化、字符串拼接、Redis key）
- 类型安全，IDE 自动补全
- Pydantic 自动解析字符串为枚举
- API 请求/响应无需转换

### 禁止的定义方式

```python
# ❌ 错误：纯 Enum（无法直接序列化为字符串）
class Gender(Enum):
    MALE = "M"

# ❌ 错误：使用 Literal 替代枚举
GenderType = Literal["M", "F", "O"]

# ❌ 错误：带 Enum 后缀
class GenderEnum(str, Enum):
    MALE = "M"
```

## 文档规范

每个枚举类**必须**有文档字符串，枚举值**建议**添加行内注释：

```python
class OrderStatus(str, Enum):
    """订单状态"""

    PENDING = "pending"      # 待支付
    PAID = "paid"            # 已支付
    CANCELLED = "cancelled"  # 已取消
    REFUNDED = "refunded"    # 已退款
```

## 导出规范

`__init__.py` 必须统一导出所有枚举，并定义 `__all__`：

```python
from .user import Gender, UserStatus
from .balance import BalanceType, TransactionType
from .order import OrderStatus, PaymentMethod
from .redemption import RedemptionCodeStatus
from .email import EmailPurpose
from .task import TaskStatus, TaskFinalStatus

__all__ = [
    "Gender",
    "UserStatus",
    "BalanceType",
    "TransactionType",
    "OrderStatus",
    "PaymentMethod",
    "RedemptionCodeStatus",
    "EmailPurpose",
    "TaskStatus",
    "TaskFinalStatus",
]
```

## 使用规范

### 导入方式

```python
# ✅ 推荐：从 enums 包直接导入
from app.core.enums import Gender, OrderStatus

# ✅ 允许：导入整个模块
from app.core import enums
status = enums.OrderStatus.PENDING

# ❌ 禁止：从子模块导入（除非在 enums 包内部）
from app.core.enums.user import Gender
```

### 比较和使用

由于枚举继承了 `str`，可以直接当作字符串使用，**禁止使用 `.value`**：

```python
# ✅ 正确：直接比较（枚举继承 str，可以和字符串比较）
if user.gender == Gender.MALE:
    ...

if status == TaskStatus.RUNNING:  # 可以和数据库/Redis 返回的字符串直接比较
    ...

# ✅ 正确：用于字符串拼接（因为继承了 str）
key = f"order:{OrderStatus.PENDING}:{order_id}"

# ✅ 正确：用于日志输出（自动转为字符串）
logger.info(f"当前状态: {status}")

# ✅ 正确：用于 Pydantic 模型
class UserCreate(BaseModel):
    gender: Gender = Gender.OTHER

# ✅ 正确：用于集合定义
TERMINAL_STATUSES = {TaskStatus.ERROR, TaskStatus.COMPLETED, TaskStatus.STOPPED}

# ❌ 错误：使用 .value 进行比较（多此一举）
if user.gender == Gender.MALE.value:
    ...

# ❌ 错误：使用 .value 获取字符串值（直接使用枚举即可）
status_str = TaskStatus.RUNNING.value  # 应该直接用 TaskStatus.RUNNING
```

## 新增枚举流程

1. 在 `app/core/enums/` 下对应文件中添加枚举类
2. 在 `__init__.py` 中导出
3. 更新 `__all__` 列表

## 违规模式检测

发现以下情况应立即指出并给出修复建议：

- 枚举类定义在 `app/core/enums/` 以外的位置（服务层内部枚举除外）
- 枚举类名带有 `Enum` 后缀
- 使用纯 `Enum` 而非 `str, Enum`
- 使用 `Literal` 替代枚举
- 枚举值命名不符合 UPPER_SNAKE_CASE
- 枚举类缺少文档字符串
- 从子模块直接导入枚举（应从 `app.core.enums` 导入）
- **使用 `.value` 获取枚举值**（`str, Enum` 可直接当字符串使用）
