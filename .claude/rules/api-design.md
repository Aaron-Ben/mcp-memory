# 接口设计规范

## 基本原则

1. 所有接口必须使用 **RESTful** 设计风格
2. 接口命名必须清晰且具有描述性，避免模糊或缩写
3. 接口只允许使用 **GET** 和 **POST** 两种 HTTP 方法
4. 接口路由必须遵循**小写加下划线**命名规范（禁止驼峰或中划线）

## 架构分层规范

```
app/
├── core/
│   ├── schemas/     # 响应模型 (Response, List)
│   ├── crud/        # 数据库 CRUD 操作（仅供 Service 层调用）
│   ├── models/      # 数据库表模型
│   └── services/    # 业务逻辑层（Router 唯一调用入口）
├── auth/            # 认证（JWT、密码）
├── db/              # 数据库连接与会话
├── dependencies/    # FastAPI 依赖注入
└── api/routers/{module}/
    ├── model.py     # API 请求模型 (CreateRequest, UpdateRequest)
    └── router.py    # 路由逻辑（只调用 Service）
```

## 分层调用规范

### 调用链路

```
Router → Service → CRUD → Database
```

### 禁止的调用方式

```python
# ❌ 错误：Router 直接调用 CRUD
from app.core.crud.user import user_crud

@router.post("/create")
async def create_user(request: CreateRequest, db: AsyncSession = Depends(get_db)):
    user = await user_crud.create(db, obj_in=UserCreate(**request.model_dump()))
    return success_response(data=user)
```

### 正确的调用方式

```python
# ✅ 正确：Router 调用 Service
from app.core.services.user import UserService

_service = UserService()

@router.post("/create")
async def create_user(request: CreateRequest, db: AsyncSession = Depends(get_db)):
    result = await _service.create(db=db, data=request.model_dump())

    if not result.success:
        return error_response(message=result.message, code=result.get_http_code())

    return success_response(data=result.data, message=result.message)
```

## Router 层规范

### 标准模式

Router 层职责：
1. 接收请求参数
2. 调用 Service 层
3. 根据 `ServiceResult` 返回响应

```python
from app.api.response import error_response, success_response
from app.core.services.xxx import XxxService

_service = XxxService()

@router.post("/list")
async def list_items(
    request: ListRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取列表"""
    result = await _service.get_list(
        db=db,
        user_id=str(current_user.user_id),
        pagination=PaginationParams(page=request.page, per_page=request.per_page),
    )

    if not result.success:
        return error_response(message=result.message, code=result.get_http_code())

    return success_response(data=result.data)
```

### Router 层禁止事项

- **禁止**直接导入和调用 CRUD 模块
- **禁止**包含业务逻辑（如权限判断、数据校验、状态流转等）
- **禁止**直接操作数据库模型
- **禁止**使用 try-catch 包裹整个处理逻辑（参见 error-handling.md）

## Service 层规范

### 职责

- 封装业务逻辑
- 调用 CRUD 层进行数据库操作
- 返回 `ServiceResult` 对象
- 数据库模型转换为响应模型

### 标准模式

```python
from app.core.services.common import ServiceResult


class XxxService:
    async def create(self, db: AsyncSession, *, obj_in: XxxCreate) -> ServiceResult:
        # 1. 业务校验
        existing = await xxx_crud.get_by_name(db, name=obj_in.name)
        if existing:
            return ServiceResult.conflict("资源已存在")

        # 2. 调用 CRUD 创建（传 schema 对象，不传 dict）
        obj = await xxx_crud.create(db, obj_in=obj_in)

        # 3. 转换为响应模型并返回
        response = XxxResponse.model_validate(obj)
        return ServiceResult.ok(data=response, message="创建成功")
```

### 分页数据返回规范

Service 层返回分页数据时，**必须**使用 `PaginatedResult.create()` 而不是手动构造字典：

```python
from app.core.services.common import PaginatedResult, PaginationParams, ServiceResult

class XxxService:
    async def get_list(
        self,
        db: AsyncSession,
        user_id: str,
        pagination: PaginationParams,
    ) -> ServiceResult[PaginatedResult[XxxResponse]]:
        """获取列表"""
        # 1. 查询数据和总数
        items_db = await xxx_crud.get_by_user_id(
            db, user_id=user_id, skip=pagination.skip, limit=pagination.limit
        )
        total = await xxx_crud.count_by_user_id(db, user_id=user_id)

        # 2. 转换为响应模型
        items = [XxxResponse.model_validate(item) for item in items_db]

        # 3. 使用 PaginatedResult.create() 返回
        result = PaginatedResult.create(items=items, total=total, pagination=pagination)
        return ServiceResult.ok(data=result)
```

**禁止的方式**：

```python
# ❌ 错误：手动构造分页字典
return ServiceResult.ok(
    data={
        "items": items,
        "total": total,
        "page": pagination.page,
        "per_page": pagination.per_page,
    }
)
```

## CRUD 层规范

CRUD 层只做数据库读写，是 Service 层的唯一数据库出入口，不承载业务逻辑、不做模型转换。

### 入参规范

- `create` 入参统一命名为 `obj_in`，类型为对应的 `XxxCreate` schema。
- `update`（针对已取出的 ORM 对象）入参统一为 `obj_in: XxxUpdate`，内部用 `model_dump(exclude_unset=True)` 只更新显式传入的字段。
- ORM 之外的字段（如 `user_id`、生成的 `xxx_id`）作为独立关键字参数追加，不塞进 schema。
- **禁止** `**kwargs`、`data: dict[str, Any]`、`obj_in: dict` 等无类型约束的入参——它们绕过类型检查，把字段错误推迟到运行期，违反「禁止隐式 Any」。
- 调用方（Service 层）必须传入 schema 对象，**禁止**传 dict 给 `obj_in`（如 `obj_in=request.model_dump()`、`obj_in=data` 均为反模式）。

```python
# ✅ 正确：schema 入参，额外字段作为独立关键字参数，一步构造
async def create(self, db: AsyncSession, *, obj_in: XxxCreate, user_id: str) -> Xxx:
    db_obj = Xxx(**obj_in.model_dump(), user_id=user_id)
    db.add(db_obj)
    await db.flush()
    await db.refresh(db_obj)
    return db_obj

# ✅ 正确：update 用 exclude_unset
async def update(self, db: AsyncSession, *, db_obj: Xxx, obj_in: XxxUpdate) -> Xxx:
    for field, value in obj_in.model_dump(exclude_unset=True).items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    await db.flush()
    await db.refresh(db_obj)
    return db_obj

# ❌ 错误：无类型约束的入参
async def create(self, db: AsyncSession, **kwargs) -> Xxx: ...
async def create(self, db: AsyncSession, *, data: dict[str, Any]) -> Xxx: ...

# ❌ 错误：create 内「先 dump 成 dict 再塞字段」两步构造
obj_data = obj_in.model_dump()
obj_data["user_id"] = user_id
db_obj = Xxx(**obj_data)  # 应合并为 Xxx(**obj_in.model_dump(), user_id=user_id)
```

### 返回值规范

- CRUD 方法**只返回 ORM 模型**（或 `None` / `list[ORM]` / 标量 / `bool`）。
- **禁止**返回 `XxxResponse`、`XxxSchema` 等响应模型，**禁止**在 CRUD 内调用 `XxxResponse.model_validate(...)`——模型转换是 Service 层的职责。
- 不要为了规避「不能返回 Response」而同时提供「返 Response 的 get」和「返 ORM 的 get_for_update」两个重复方法；统一返回 ORM 即可，转换交给 Service。

```python
# ✅ 正确：返回 ORM
async def get_by_id(self, db: AsyncSession, resource_id: str) -> Xxx | None:
    result = await db.execute(select(Xxx).where(Xxx.id == resource_id))
    return result.scalars().first()

# ❌ 错误：CRUD 返回 Response（模型转换越权到 CRUD 层）
async def get_by_id(self, db: AsyncSession, resource_id: str) -> XxxResponse | None:
    ...
    return XxxResponse.model_validate(obj)
```

### 时间字段规范

服务器侧生成的时间（如 `rewarded_at`、`paid_at`）由 Service 层赋值并通过 schema 传入，**禁止**在 CRUD 内硬算 `time_utils.now()`（详见 database.md「Service 层时间赋值」）。

## Schema 导入规范

- `model.py` 中**禁止**导入 `app.core.schemas` 中的 CRUD 模型（Create, Update 等）
- `model.py` 中的 Request 模型必须**直接展开**所有字段定义，不允许嵌套引用
- `router.py` 中从 `app.core.schemas` 导入响应模型（用于 `response_model` 声明）
- 遵循「谁使用谁导入」原则

## Request 模型设计规范

- `CreateRequest`：直接展开所有需要的字段
- `UpdateRequest`：包含标识字段（如 id）+ 所有可更新字段
- `GetRequest`：包含标识字段
- `ListRequest`：包含分页参数 + 筛选条件
- **禁止**在 Request 模型中使用嵌套的 schemas 对象作为字段类型

```python
# ❌ 错误示例
class CreateRequest(BaseModel):
    config: MCPConfigCreate  # 禁止嵌套引用

# ✅ 正确示例
class CreateRequest(BaseModel):
    key: str
    value: Dict[str, Any]
    # ... 直接展开所有字段
```

## 响应数据规范

### Service 层负责模型转换

数据库模型到响应模型的转换在 **Service 层**完成，Router 层直接使用 `result.data`：

```python
# Service 层
async def get_by_id(self, db: AsyncSession, resource_id: str) -> ServiceResult:
    obj = await crud.get(db, id=resource_id)
    if not obj:
        return ServiceResult.not_found("资源不存在")

    # 在 Service 层完成模型转换
    response = ResourceResponse.model_validate(obj)
    return ServiceResult.ok(data=response)

# Router 层 - 直接使用 result.data
@router.post("/get")
async def get_resource(request: GetRequest, db: AsyncSession = Depends(get_db)):
    result = await _service.get_by_id(db=db, resource_id=request.id)

    if not result.success:
        return error_response(message=result.message, code=result.get_http_code())

    return success_response(data=result.data)  # 已经是响应模型
```

### 响应模型配置

所有响应模型必须配置：

```python
class XxxResponse(BaseModel):
    model_config = {"from_attributes": True}
```

## 违规模式检测

发现以下情况应立即指出并给出修复建议：

- Router 层直接导入或调用 CRUD 模块
- Router 层包含业务逻辑代码
- Router 层进行数据库模型转换（应在 Service 层完成）
- `model.py` 中导入了 `app.core.schemas` 中的 CRUD 模型
- Request 模型中使用嵌套的 schemas 对象作为字段
- Service 层未返回 `ServiceResult` 对象
- 响应模型未配置 `model_config = {"from_attributes": True}`
- **Service 层返回分页数据时手动构造字典**（应使用 `PaginatedResult.create()`）
