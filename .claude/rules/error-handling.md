# 错误处理规范

## 分层错误处理架构

项目采用**两层错误处理机制**，Router 层不需要显式 try-catch：

| 层级 | 处理方式 | 处理的错误类型 |
|------|----------|----------------|
| **Service 层** | 返回 `ServiceResult(success=False)` | 业务逻辑错误（如：资源不存在、无权限、参数无效等） |
| **全局异常处理器** | `global_exception_handler` | 意外异常（如：数据库连接失败、网络超时、代码 bug 等） |

## Router 层规范

### 标准模式

Router 层只需检查 `ServiceResult.success` 来处理业务逻辑结果：

```python
# ✅ 正确：通过 ServiceResult 处理业务错误
@router.post("/create")
async def create_resource(request: CreateRequest, db: AsyncSession = Depends(get_db)):
    result = await service.create(db=db, data=request.model_dump())

    if not result.success:
        return error_response(message=result.message, code=result.get_http_code())

    return success_response(data=result.data, message=result.message)
```

### 禁止的模式

```python
# ❌ 错误：Router 层不需要显式 try-catch（全局处理器会兜底）
@router.post("/create")
async def create_resource(request: CreateRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await service.create(db=db, data=request.model_dump())
        if not result.success:
            return error_response(message=result.message)
        return success_response(data=result.data)
    except Exception as e:
        return error_response(message="服务器错误")  # 多余的，全局处理器已处理
```

## Service 层规范

### 业务错误处理

Service 层必须捕获**可预期的业务异常**，并转换为 `ServiceResult`：

```python
# ✅ 正确：业务逻辑错误返回失败结果
async def get_by_id(self, db: AsyncSession, resource_id: str) -> ServiceResult:
    resource = await crud.get(db, id=resource_id)

    if not resource:
        return ServiceResult.not_found("资源不存在")

    if resource.user_id != current_user_id:
        return ServiceResult.forbidden("无权访问此资源")

    return ServiceResult.ok(data=ResourceResponse.model_validate(resource))
```

### 意外异常处理

对于**不可预期的异常**，有两种策略：

#### 策略一：让异常冒泡（推荐）

让全局处理器统一处理，适用于大部分场景：

```python
# ✅ 推荐：不捕获意外异常，让全局处理器处理
async def create(self, db: AsyncSession, data: dict) -> ServiceResult:
    obj = await crud.create(db, obj_in=data)  # 数据库异常会向上冒泡
    return ServiceResult.ok(data=obj)
```

#### 策略二：捕获并转换（特殊场景）

需要返回特定错误信息时：

```python
# ✅ 特殊场景：需要自定义错误信息
async def create(self, db: AsyncSession, data: dict) -> ServiceResult:
    try:
        obj = await crud.create(db, obj_in=data)
        return ServiceResult.ok(data=obj)
    except IntegrityError:
        return ServiceResult.conflict("资源已存在，请勿重复创建")
```

## 全局异常处理器

位于 `app/api/exceptions.py`，已注册以下处理器：

| 处理器 | 异常类型 | 说明 |
|--------|----------|------|
| `validation_exception_handler` | `RequestValidationError` | 请求参数验证失败（422） |
| `http_exception_handler` | `HTTPException` | HTTP 异常 |
| `global_exception_handler` | `Exception` | 所有未捕获的异常（500） |

### 异常处理流程

```
请求 → Router → Service → CRUD/外部服务
                  ↓
            发生异常？
           ↙        ↘
         是          否
          ↓           ↓
    业务异常？    返回成功结果
   ↙        ↘
  是         否
   ↓          ↓
返回失败    冒泡到全局处理器
ServiceResult  → 记录日志 + 上报 Sentry
               → 返回 500 错误
```

## ServiceResult 规范

### 标准工厂方法

```python
# 成功
ServiceResult.ok(data=response_data, message="操作成功")

# 业务错误
ServiceResult.failure(message="操作失败", code=ErrorCode.BUSINESS_ERROR)
ServiceResult.not_found(message="资源不存在")
ServiceResult.forbidden(message="无权限")
ServiceResult.conflict(message="资源冲突")
ServiceResult.bad_request(message="参数无效")
```

### HTTP 状态码映射

| ErrorCode | HTTP Status | 说明 |
|-----------|-------------|------|
| `SUCCESS` | 200 | 成功 |
| `BAD_REQUEST` | 400 | 请求参数错误 |
| `UNAUTHORIZED` | 401 | 未认证 |
| `FORBIDDEN` | 403 | 无权限 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `CONFLICT` | 409 | 资源冲突 |
| `BUSINESS_ERROR` | 422 | 业务逻辑错误 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |

## 违规模式检测

发现以下情况应立即指出并给出修复建议：

- Router 层使用了不必要的 try-catch 包裹整个处理逻辑
- Service 层直接抛出异常而不是返回 `ServiceResult.failure()`
- 使用裸 `except:` 或 `except Exception:` 吞掉所有异常
- 未检查 `ServiceResult.success` 就直接使用 `result.data`
