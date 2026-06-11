# Protobuf / gRPC 代码生成规范

## 生成命令

**必须**在项目根目录执行，`-I .` 从根路径解析，确保生成的 import 带完整包路径：

```bash
python -m grpc_tools.protoc \
  -I . \
  --python_out=. \
  --grpc_python_out=. \
  --pyi_out=. \
  app/proto/<name>.proto
```

**禁止**使用 `-I app/proto`，这会导致生成裸 `import <name>_pb2`，在包内运行时报 `ModuleNotFoundError`。

## 生成后验证

检查 `*_pb2_grpc.py` 中的 import 是否带包路径：

```python
# ✅ 正确
from app.proto import memory_pb2 as memory__pb2

# ❌ 错误（用了 -I app/proto 生成）
import memory_pb2 as memory__pb2
```
