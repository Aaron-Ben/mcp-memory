# 异步编程规范

## 异步风格一致性

同一类/模块中的方法必须保持异步风格的一致性：

- 如果类中大部分方法是异步的（`async def`），则所有公开方法都应该是异步的
- 避免同一个类中混用同步和异步方法，除非有明确的设计理由

## 异步方法调用规范

异步方法的定义和调用必须匹配：

```python
# ✅ 正确
result = await async_method()

# ❌ 错误 - 返回协程对象而非实际结果
result = async_method()
```

- 定义为 `async def` 的方法，调用时**必须**使用 `await`
- 禁止遗漏 `await` 关键字

## 纯计算方法例外

不涉及 I/O 操作的纯数据处理方法可以保持同步：

- `to_dict()`、`get_xxx()` 等纯计算方法可以保持同步
- 但如果该方法所在的类在异步上下文中使用，建议统一为异步以保持一致性

## 异步 I/O 规范

异步请求路径、MCP tool 执行路径和 worker 热路径禁止使用阻塞文件 I/O。

### 基本要求

- 异步服务路径使用 `aiofiles` 进行文件操作。
- `async def` 中读取大文件、写文件、删除文件时使用异步 I/O。
- 启动期配置读取、迁移脚本、小型 CLI 可以使用同步文件 I/O，但不能出现在高频异步请求路径。

### 正确示例

```python
import aiofiles

# ✅ 正确：异步读取文件
async def read_config():
    async with aiofiles.open("config.json", "r", encoding="utf-8") as f:
        content = await f.read()
        return json.loads(content)

# ✅ 正确：异步写入文件
async def save_data(data: bytes):
    async with aiofiles.open("output.bin", "wb") as f:
        await f.write(data)
```

### 错误示例

```python
# ❌ 错误：使用同步 open()
async def read_config():
    with open("config.json", "r") as f:
        content = f.read()
        return json.loads(content)

# ❌ 错误：在异步方法中使用同步文件操作
async def save_data(data: bytes):
    with open("output.bin", "wb") as f:
        f.write(data)
```

### 文件操作对照表

| 同步操作 | 异步操作 |
|---------|---------|
| `with open(path, "r") as f:` | `async with aiofiles.open(path, "r") as f:` |
| `content = f.read()` | `content = await f.read()` |
| `f.write(data)` | `await f.write(data)` |
| `os.path.exists(path)` | `await aiofiles.os.path.exists(path)` |
| `os.remove(path)` | `await aiofiles.os.remove(path)` |

### 特殊场景

#### 临时文件处理

```python
import tempfile
import uuid
import os

# ✅ 正确：创建临时文件路径，然后异步写入
temp_path = os.path.join(tempfile.gettempdir(), f"temp_{uuid.uuid4().hex}.dat")
async with aiofiles.open(temp_path, "wb") as f:
    await f.write(data)
```

#### JSON 文件处理

```python
import json

# ✅ 正确：先异步读取，再解析 JSON
async with aiofiles.open("data.json", "r", encoding="utf-8") as f:
    content = await f.read()
    data = json.loads(content)

# ✅ 正确：先序列化 JSON，再异步写入
json_str = json.dumps(data, ensure_ascii=False, indent=2)
async with aiofiles.open("data.json", "w", encoding="utf-8") as f:
    await f.write(json_str)
```

## 违规模式检测

发现以下情况应立即指出并给出修复建议：

- 同一类中方法的异步风格不一致（部分 `async def`，部分普通 `def`）
- 调用异步方法时遗漏 `await` 关键字
- 在同步上下文中错误地调用异步方法
- 在异步请求路径中使用同步的 `open()` 函数
- 在异步请求路径中执行大文件同步读写
- 在 worker 热路径中使用阻塞文件系统操作
