# 代码风格规范

## 文件规模指标

1. **动态语言**（Python、JavaScript、TypeScript 等）：每个代码文件建议不超过 **300 行**，模型定义等字段密集型文件可放宽至 **400 行**，但超过 300 行时必须审视是否存在可拆分的独立职责
2. **静态语言**（Java、Go、Rust 等）：每个代码文件建议不超过 **350 行**，同上
3. **文件夹结构**：每层文件夹中的文件不超过 **8 个**，超过时需规划为多层子文件夹

## 编码规范

- 所有中文必须使用 **UTF-8** 编码保存
- 禁止使用 GBK、GB2312 等其他编码格式

## Python 专项规范

### 命名约定

| 类型 | 规范 | 示例 |
|------|------|------|
| **内部函数/方法** | 仅供模块内部使用的函数，必须以下划线开头 | `_parse_data()`、`_validate()` |
| **内部类** | 仅供模块内部使用的类，必须以下划线开头 | `_InternalParser` |
| **常量** | 全大写 + 下划线分隔 | `MAX_RETRY_COUNT`、`DEFAULT_TIMEOUT` |
| **私有属性** | 双下划线开头（触发名称改写） | `self.__secret_key` |
| **类名** | 大驼峰命名（PascalCase） | `UserManager`、`HttpClient` |
| **函数/变量名** | 小写 + 下划线分隔（snake_case） | `get_user_info`、`total_count` |

### 导入规范

```python
# ✅ 正确的导入顺序（按组分隔，每组内按字母排序）
import os  # 1. 标准库
import sys
from typing import Dict, List

import httpx  # 2. 第三方库
from pydantic import BaseModel

from app.config import settings  # 3. 本地模块
from utils.logger import logger
```

**禁止的导入方式：**

```python
# ❌ 禁止通配符导入
from module import *

# ❌ 禁止循环导入（A 导入 B，B 又导入 A）

# ❌ 禁止在函数内部导入（除非解决循环依赖）
def my_func():
    import some_module  # 应移到文件顶部
```

### `__all__` 导出控制

- 聚合导出模块（如 `__init__.py`）**必须**定义 `__all__` 列表，明确声明对外暴露的接口
- 普通业务模块（如 `service.py`、`router.py`）不强制要求

```python
# my_module.py
__all__ = ["PublicClass", "public_function"]

class PublicClass:
    pass

class _InternalClass:  # 内部类，不在 __all__ 中
    pass
```

### 类型注解

- 所有公开函数/方法**必须**添加类型注解
- 内部函数建议添加类型注解
- **必须使用 Python 3.10+ 现代类型语法**，禁止使用 `typing` 模块中的旧泛型别名

```python
# ✅ 正确：使用现代语法（Python 3.10+）
def get_user(user_id: int) -> dict[str, Any] | None:
    ...

def process_items(items: list[str]) -> list[str]:
    ...

def get_mapping() -> dict[str, list[int]]:
    ...

# ❌ 错误：使用 typing 旧泛型别名
from typing import Optional, List, Dict
def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    ...
```

**类型语法对照表**：

| 旧语法（禁止） | 新语法（必须） |
|----------------|---------------|
| `Optional[X]` | `X \| None` |
| `List[X]` | `list[X]` |
| `Dict[K, V]` | `dict[K, V]` |
| `Tuple[X, Y]` | `tuple[X, Y]` |
| `Set[X]` | `set[X]` |
| `Union[X, Y]` | `X \| Y` |

> **注意**：`typing` 模块中的高阶类型工具（`TypeVar`、`Generic`、`Protocol`、`TypedDict`、`Literal`、`Final`、`Callable`、`Any`）仍然从 `typing` 导入使用。

### mypy 类型检查规范

虽然 pre-commit 中未强制运行 mypy，但编写代码时**必须**遵循 mypy 类型检查规范，确保类型安全：

#### 基本要求

| 规则 | 说明 |
|------|------|
| **禁止隐式 Any** | 不允许使用未标注类型的变量、参数或返回值 |
| **严格可选类型** | `Optional[T]` 必须显式处理 `None` 情况 |
| **禁止隐式重导出** | 模块中导入的符号不会自动导出，需通过 `__all__` 显式声明 |

#### 常见类型错误及修复

```python
# ❌ 错误：参数缺少类型注解
def process(data):
    return data.strip()

# ✅ 正确：添加类型注解
def process(data: str) -> str:
    return data.strip()
```

```python
# ❌ 错误：未处理 Optional 的 None 情况
def get_name(user: User | None) -> str:
    return user.name  # mypy 报错：user 可能为 None

# ✅ 正确：显式处理 None
def get_name(user: User | None) -> str:
    if user is None:
        return "Unknown"
    return user.name
```

```python
# ❌ 错误：字典类型不明确
def get_config() -> dict:
    return {"key": "value"}

# ✅ 正确：明确字典键值类型
def get_config() -> dict[str, str]:
    return {"key": "value"}
```

```python
# ❌ 错误：列表类型不明确
def get_ids() -> list:
    return [1, 2, 3]

# ✅ 正确：明确列表元素类型
def get_ids() -> list[int]:
    return [1, 2, 3]
```

#### 类型忽略注释

仅在确实无法添加正确类型时使用 `# type: ignore`，且**必须**说明原因：

```python
# ✅ 正确：说明忽略原因
result = external_lib.call()  # type: ignore[no-untyped-call]  # 第三方库无类型桩

# ❌ 错误：无理由忽略
result = some_function()  # type: ignore
```

#### 推荐的类型工具

| 类型 | 用途 | 示例 |
|------|------|------|
| `TypeVar` | 泛型类型变量 | `T = TypeVar("T")` |
| `Generic` | 泛型类 | `class Container(Generic[T])` |
| `Protocol` | 结构化子类型 | `class Readable(Protocol)` |
| `TypedDict` | 类型化字典 | `class UserDict(TypedDict)` |
| `Literal` | 字面量类型 | `Literal["read", "write"]` |
| `Final` | 常量标记 | `MAX_SIZE: Final = 100` |
| `Callable` | 可调用类型 | `Callable[[int], str]` |

#### 手动运行 mypy

建议在重要提交前手动运行 mypy 检查：

```bash
# 检查整个项目
mypy src/mcp_memory/

# 检查单个文件
mypy src/mcp_memory/services/recall.py

# 使用项目配置
mypy --config-file=pyproject.toml src/mcp_memory/
```

### 异常处理规范

```python
# ✅ 正确：捕获具体异常
try:
    result = risky_operation()
except ValueError as e:
    logger.error(f"值错误: {e}")
except ConnectionError as e:
    logger.error(f"连接错误: {e}")

# ❌ 错误：裸 except 或捕获 Exception
try:
    result = risky_operation()
except:  # 禁止
    pass

try:
    result = risky_operation()
except Exception:  # 除非在最外层兜底，否则禁止
    pass
```

### 字符串规范

```python
# ✅ 推荐：使用 f-string 格式化
name = "Alice"
message = f"Hello, {name}!"

# ❌ 避免：% 格式化和 .format()
message = "Hello, %s!" % name
message = "Hello, {}!".format(name)

# ✅ 多行字符串使用三引号
sql = """
    SELECT id, name
    FROM users
    WHERE status = 'active'
"""
```

### 函数设计规范

- 单个函数不超过 **50 行**（不含空行和注释）
- 函数参数不超过 **5 个**，超过时使用数据类或字典
- 避免可变默认参数

```python
# ❌ 错误：可变默认参数
def add_item(item, items=[]):
    items.append(item)
    return items

# ✅ 正确：使用 None 作为默认值
def add_item(item: str, items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    items.append(item)
    return items
```

### 上下文管理器

```python
# ✅ 推荐：使用 async with 管理资源（异步场景）
async with aiofiles.open("file.txt", "r") as f:
    content = await f.read()

async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()

# ❌ 禁止：手动管理资源关闭
f = open("file.txt", "r")
content = f.read()
f.close()  # 容易遗漏
```

> **注意**：异步方法中的文件 I/O 必须使用 `aiofiles`，详见 `async-programming.md`。

### 列表/字典推导式

```python
# ✅ 简单逻辑使用推导式
squares = [x ** 2 for x in range(10)]
active_users = {u.id: u for u in users if u.is_active}

# ❌ 包含两个以上条件判断或嵌套调用时，禁止使用推导式，应拆分为普通循环
result = [
    transform(x)
    for x in items
    if validate(x) and process(x) and check_status(x)
]
```

> **判断标准**：基于逻辑复杂度而非物理行数。纯因格式化换行的多行推导式可以接受，但条件判断复杂时必须拆为循环。

### 布尔表达式

```python
# ✅ 正确：直接使用布尔值
if is_valid:
    ...

if items:  # 检查非空
    ...

# ❌ 错误：冗余比较
if is_valid == True:
    ...

if len(items) > 0:
    ...
```

## 禁止向后兼容代码

> **适用范围**：本规范适用于内部应用代码。若项目作为共享库或 SDK 对外提供，需遵循版本发布流程，不适用本条。

修改代码时**禁止**添加向后兼容的过渡代码，应直接修改到位：

| 禁止的做法 | 正确的做法 |
|------------|------------|
| 重命名未使用的变量为 `_var` | 直接删除未使用的变量 |
| 为已删除的代码添加 `# removed` 注释 | 直接删除，不保留任何痕迹 |
| 重新导出已移动的类型以保持旧路径可用 | 更新所有引用到新路径 |
| 保留废弃方法并标记 `@deprecated` | 直接删除废弃方法，更新调用方 |
| 添加兼容层或适配器处理旧接口 | 直接修改接口，更新所有调用方 |

```python
# ❌ 错误：保留未使用的变量
_old_config = None  # 已废弃，保留以防万一

# ❌ 错误：添加移除注释
# removed: def legacy_method(): ...

# ❌ 错误：重新导出以保持兼容
from new_module import SomeClass
OldClassName = SomeClass  # 向后兼容别名

# ✅ 正确：直接删除，不留痕迹
# （什么都不写，干净地移除）
```

**原则**：代码应该保持干净整洁，删除即删除，修改即修改。Git 历史记录会保留所有变更，无需在代码中保留任何"考古痕迹"。

## 日志规范

### 基本要求

- **禁止使用 `print()` 输出调试信息**，必须使用项目统一的 `logger`
- 日志消息使用 f-string 格式化

### 日志级别约定

| 级别 | 使用场景 |
|------|----------|
| `DEBUG` | 开发调试信息，生产环境不输出 |
| `INFO` | 关键业务流程节点（如：用户登录、订单创建） |
| `WARNING` | 可恢复的异常情况（如：重试、降级） |
| `ERROR` | 不可恢复的错误，需要关注和处理 |

```python
from utils.logger import logger

# ✅ 正确
logger.info(f"用户 {user_id} 登录成功")
logger.error(f"支付回调处理失败: {e}")

# ❌ 错误
print(f"用户 {user_id} 登录成功")
```

## 魔术值规范

禁止在代码中直接使用含义不明的字面量数字或字符串，必须提取为**常量**或**枚举**：

```python
# ❌ 错误：魔术数字和字符串
if retry_count > 3:
    ...
if status == "pending":
    ...

# ✅ 正确：使用常量或枚举
MAX_RETRY_COUNT = 3

if retry_count > MAX_RETRY_COUNT:
    ...
if status == OrderStatus.PENDING:
    ...
```

> 显而易见的值（如 `0`、`1`、`""`、`None`）不受此限制。

## 返回值一致性

同一类型的函数/方法应返回相同类型，避免调用方需要处理多种返回形态：

```python
# ❌ 错误：同类方法返回类型不一致
class UserService:
    async def get_by_id(self, db, user_id) -> ServiceResult:
        ...  # 返回 ServiceResult

    async def get_by_email(self, db, email) -> User | None:
        ...  # 直接返回模型，风格不统一

# ✅ 正确：同类方法统一返回 ServiceResult
class UserService:
    async def get_by_id(self, db, user_id) -> ServiceResult:
        ...

    async def get_by_email(self, db, email) -> ServiceResult:
        ...
```

## 代码质量「坏味道」检测

时刻关注并避免以下侵蚀代码质量的问题：

| 问题 | 描述 |
|------|------|
| **僵化 (Rigidity)** | 系统难以变更，任何微小的改动都会引发一连串的连锁修改 |
| **冗余 (Redundancy)** | 同样的代码逻辑在多处重复出现，导致维护困难且容易产生不一致 |
| **循环依赖 (Circular Dependency)** | 两个或多个模块互相纠缠，形成无法解耦的"死结"，导致难以测试与复用 |
| **脆弱性 (Fragility)** | 对代码一处的修改，导致了系统中其他看似无关部分功能的意外损坏 |
| **晦涩性 (Obscurity)** | 代码意图不明，结构混乱，导致阅读者难以理解其功能和设计 |
| **数据泥团 (Data Clump)** | 多个数据项总是一起出现在不同方法的参数中，暗示着它们应该被组合成一个独立的对象 |
| **不必要的复杂性 (Needless Complexity)** | 用"杀牛刀"去解决"杀鸡"的问题，过度设计使系统变得臃肿且难以理解 |

## 执行要求

- 无论是编写、阅读还是审核代码时，都必须严格遵守上述规范
- 一旦识别出「坏味道」，应立即询问用户是否需要优化，并给出合理建议
- **提交代码前必须通过所有静态检查**，不允许跳过 pre-commit hooks
