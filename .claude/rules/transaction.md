# 事务管理规范

## 核心原则

**事务由上下文管理器自动管理。** 业务代码专注逻辑，不手动 commit/rollback。

## 自动事务机制

所有数据库会话（`get_db` 和 `async_db_session`）统一自动管理事务：

| 场景 | 行为 |
|------|------|
| 正常退出 | 自动 `commit` |
| 抛出异常 | 自动 `rollback` |
| 最终 | 自动 `close` |

## 分层职责

| 层级 | 事务操作 | 说明 |
|------|----------|------|
| **CRUD 层** | `await db.flush()` | 将数据同步到数据库（可获取自增 ID 等），但不提交事务 |
| **Service 层** | 无需手动 commit | 上下文管理器自动提交 |
| **Router 层** | 不直接管理事务 | 通过 `get_db` 依赖获取会话 |

## CRUD 层规范

### 禁止在 CRUD 层使用 `db.commit()`

```python
# ❌ 错误：CRUD 层提交事务
db.add(db_obj)
await db.commit()
await db.refresh(db_obj)
return db_obj

# ✅ 正确：CRUD 层只 flush
db.add(db_obj)
await db.flush()
await db.refresh(db_obj)
return db_obj
```

### ORM 对象操作（create / update ORM 字段 / 软删除）

```python
# flush 后保留 refresh，获取数据库生成的字段（自增ID、created_at等）
db.add(db_obj)
await db.flush()
await db.refresh(db_obj)
return db_obj
```

### `update()` 语句操作（批量更新、无 ORM 对象）

```python
# flush 后不能 refresh（没有 ORM 对象实例）
result = await db.execute(stmt)
await db.flush()
return result.rowcount > 0
```

## Service 层规范

### 写操作不需要手动 commit

上下文管理器在正常退出时自动 commit，Service 层直接返回结果即可：

```python
class XxxService:
    async def create(self, db: AsyncSession, data: dict) -> ServiceResult:
        # 1. 业务校验
        existing = await xxx_crud.get_by_name(db, name=data["name"])
        if existing:
            return ServiceResult.conflict("资源已存在")

        # 2. 调用 CRUD 写操作（flush，未提交）
        obj = await xxx_crud.create(db, obj_in=data)

        # 3. 转换并返回（无需 commit，自动提交）
        response = XxxResponse.model_validate(obj)
        return ServiceResult.ok(data=response, message="创建成功")
```

### 多个 CRUD 写操作的原子性

多个 CRUD 操作共享同一个 db session，自动成为一个原子事务：

```python
async def transfer_credits(self, db: AsyncSession, ...) -> ServiceResult:
    await credits_crud.update_recharge_credits(db, user_id=user_id, amount=-amount)
    await transaction_crud.record_transaction(db, ...)

    # 无需手动 commit，正常退出后自动提交
    # 任一操作抛出异常则自动 rollback
    return ServiceResult.ok(data=result, message="转账成功")
```

### 读操作无影响

纯读操作的 Service 方法无需任何事务操作（commit 空事务开销可忽略）：

```python
async def get_by_id(self, db: AsyncSession, resource_id: str) -> ServiceResult:
    obj = await xxx_crud.get(db, id=resource_id)
    if not obj:
        return ServiceResult.not_found("资源不存在")
    response = XxxResponse.model_validate(obj)
    return ServiceResult.ok(data=response)
```

## 数据库会话获取方式

| 方式 | 行为 | 使用场景 |
|------|------|----------|
| `get_db` | 自动 commit/rollback/close | Router 依赖注入 |
| `async_db_session` | 自动 commit/rollback/close | 脚本、定时任务、后台任务等非依赖注入场景 |

两者事务行为完全一致，区别仅在于获取方式：

```python
# Router 依赖注入
@router.post("/create")
async def create(db: AsyncSession = Depends(get_db)):
    ...

# 非依赖注入场景
async with async_db_session() as db:
    await some_crud.create(db, obj_in=data)
    # 无需 commit，退出 async with 时自动提交
```

## 违规模式检测

发现以下情况应立即指出并给出修复建议：

- **CRUD 层使用 `await db.commit()`**（应使用 `await db.flush()`）
- **`update()` 语句后调用 `db.refresh()`**（无 ORM 对象实例，会报错）
- **任何位置手动调用 `await db.commit()`**（应由上下文管理器自动提交）
- **手动调用 `await db.rollback()`**（应由上下文管理器自动回滚）
