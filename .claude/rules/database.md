# 数据库规范

## 时间字段规范

### 统一使用 DateTime 类型

所有时间字段**必须**使用 `DateTime(timezone=False)` 类型，存储无时区的东八区本地时间：

```python
from sqlalchemy import Column, DateTime
from app.core.models.base import BaseModel, get_china_time

class MyModel(BaseModel):
    # ✅ 正确：使用 DateTime 类型
    created_at = Column(DateTime(timezone=False), default=get_china_time, comment="创建时间")
    updated_at = Column(DateTime(timezone=False), default=get_china_time, onupdate=get_china_time, comment="更新时间")
    redeemed_at = Column(DateTime(timezone=False), nullable=True, comment="兑换时间")

    # ❌ 错误：使用 String 存储时间
    redeemed_at = Column(String(50), nullable=True, comment="兑换时间")
```

### Schema 中的时间类型

对应的 Pydantic Schema 也必须使用 `datetime` 类型：

```python
from datetime import datetime
from pydantic import BaseModel

class MyResponse(BaseModel):
    # ✅ 正确
    created_at: datetime
    redeemed_at: datetime | None = None

    # ❌ 错误
    redeemed_at: str | None = None

    model_config = {"from_attributes": True}
```

### Service 层时间赋值

Service 层赋值时间字段时，直接使用 `time_utils.now()` 返回的 datetime 对象：

```python
from utils.time_utils import time_utils

# ✅ 正确：直接使用 datetime 对象
update_data = SomeUpdate(
    redeemed_at=time_utils.now(),
)

# ❌ 错误：转换为字符串
now_str = time_utils.now().strftime("%Y-%m-%d %H:%M:%S")
update_data = SomeUpdate(
    redeemed_at=now_str,
)
```

## 数据库迁移规范

### PostgreSQL 类型转换

当修改字段类型（如 `VARCHAR` → `TIMESTAMP`）时，PostgreSQL 无法自动转换，需要手动修改迁移文件：

```python
# ❌ 错误：自动生成的迁移无法执行
def upgrade() -> None:
    op.alter_column('table_name', 'column_name',
               existing_type=sa.VARCHAR(length=50),
               type_=sa.DateTime(),
               existing_nullable=True)

# ✅ 正确：使用原生 SQL 并指定 USING 子句
def upgrade() -> None:
    op.execute(
        "ALTER TABLE table_name "
        "ALTER COLUMN column_name TYPE TIMESTAMP WITHOUT TIME ZONE "
        "USING column_name::timestamp without time zone"
    )
```

### 迁移执行流程

1. 生成迁移文件：`alembic revision --autogenerate -m "描述"`
2. **检查迁移文件**：确认是否需要手动调整（特别是类型转换）
3. 执行迁移：`alembic upgrade head`
4. 验证迁移结果

### 新增模型必须注册到 `__init__.py`

新建 ORM 模型文件后，**必须**在 `app/core/models/__init__.py` 中导入并加入 `__all__`。

`autogenerate` 通过 `Base.metadata` 感知模型，而模型只有被导入后才会注册到 `Base.metadata`。`migrations/env.py` 仅靠 `import app.core.models` 触发 `__init__.py` 完成注册——**未导入的模型不在 metadata 中**。

后果：漏注册的模型会被 `autogenerate` 当成"数据库里多余的表"，生成 `drop_table`。若未察觉直接 `upgrade`，**线上表和数据会被删除**。

```python
# 新增 app/core/models/subscription.py 后，必须补全 __init__.py：
from .subscription import Subscription   # 1. 导入

__all__ = [
    ...
    "Subscription",                       # 2. 加入 __all__
]
```

> **检查信号**：若 `autogenerate` 生成的迁移里出现 `op.drop_table(...)` 删的是仍在使用的表，几乎都是模型漏注册，先排查 `__init__.py`，**不要执行该迁移**。

## 布尔字段查询规范

### 禁止使用 Python 的 `is` 运算符

在 SQLAlchemy 查询中，**禁止**使用 Python 的 `is` 运算符比较列字段：

```python
# ❌ 错误：使用 is 运算符（无法生成 SQL 查询条件）
select(User).where(User.is_deleted is False)
select(User).where(User.is_active is True)

# ✅ 首选：使用 .is_() 方法（生成 SQL IS 语法，NULL 安全）
select(User).where(User.is_deleted.is_(False))
select(User).where(User.is_active.is_(True))

# ✅ 可选：布尔字段的简写形式
select(User).where(User.is_active)           # 等价于 .is_(True)
select(User).where(~User.is_deleted)         # 等价于 .is_(False)

# ⚠️ 不推荐：使用 == 运算符（虽然可用，但不如 .is_() 明确）
select(User).where(User.is_deleted == False)
select(User).where(User.is_active == True)
```

### 原因说明

| 问题 | 说明 |
|------|------|
| **`is` 的本质** | Python 的 `is` 用于比较对象身份（内存地址），而非值 |
| **无法重载** | `is` 运算符在 Python 中无法被重载，SQLAlchemy 无法拦截并转换 |
| **错误后果** | `User.is_deleted is False` 只会比较列对象本身与 `False` 的身份，不会生成 SQL 条件 |

### 推荐写法（优先级从高到低）

| 场景 | 推荐写法 | 生成的 SQL | 优先级 |
|------|----------|------------|--------|
| 检查为真 | `User.is_active.is_(True)` | `WHERE is_active IS TRUE` | ⭐ 首选 |
| 检查为假 | `User.is_deleted.is_(False)` | `WHERE is_deleted IS FALSE` | ⭐ 首选 |
| 检查为真（简写） | `User.is_active` | `WHERE is_active = true` | 可选 |
| 检查为假（简写） | `~User.is_deleted` | `WHERE is_deleted = false` | 可选 |
| 检查为真（兼容） | `User.is_active == True` | `WHERE is_active = true` | 不推荐 |
| 检查为假（兼容） | `User.is_deleted == False` | `WHERE is_deleted = false` | 不推荐 |

### 复合条件示例

```python
from sqlalchemy import and_, or_, select

# ✅ 首选：使用 .is_() 方法
stmt = select(User).where(
    and_(
        User.user_id.in_(user_ids),
        User.is_deleted.is_(False),
        User.is_active.is_(True),
    )
)

# ✅ 可选：使用简写形式
stmt = select(User).where(
    and_(
        User.user_id.in_(user_ids),
        ~User.is_deleted,
        User.is_active,
    )
)

# ❌ 错误：使用 is 运算符
stmt = select(User).where(
    and_(
        User.user_id.in_(user_ids),
        User.is_deleted is False,  # 不会生成 SQL 条件！
    )
)
```

## 违规模式检测

发现以下情况应立即指出并给出修复建议：

- 时间字段使用 `String` 类型而非 `DateTime`
- Schema 中时间字段使用 `str` 类型而非 `datetime`
- Service 层将时间转换为字符串后存储
- 迁移文件中类型转换未添加 `USING` 子句
- **查询条件中使用 `is` 运算符比较列字段**（应使用 `==`、`.is_()` 或简写形式）
