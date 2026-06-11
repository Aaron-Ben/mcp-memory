# MCP Memory 项目规范

本项目遵循严格的代码质量和架构设计标准。详细规范请参阅 `.claude/rules/` 目录下的规则文件。

## 规则文件索引

| 文件                                                 | 职责                             |
|----------------------------------------------------|--------------------------------|
| [code-style.md](rules/code-style.md)               | 代码风格、文件规模、编码规范、代码质量检测          |
| [api-design.md](rules/api-design.md)               | RESTful 接口设计、架构分层、CRUD 层规范、模型转换规范 |
| [async-programming.md](rules/async-programming.md) | 异步编程风格一致性、await 调用规范           |
| [error-handling.md](rules/error-handling.md)       | 分层错误处理、ServiceResult 规范、全局异常处理 |
| [database.md](rules/database.md)                   | 数据库字段规范、时间类型、迁移规范              |
| [transaction.md](rules/transaction.md)             | 事务管理规范                         |
| [enums.md](rules/enums.md)                         | 枚举类定义、导出和使用规范                  |
| [comments.md](rules/comments.md)                   | 注释规范、文档字符串、代码即文档原则             |
| [protobuf.md](rules/protobuf.md)                   | Protobuf/gRPC 代码生成命令、import 规范   |

## 执行要求

- 无论是编写、阅读还是审核代码时，都必须严格遵守各规则文件中的规范
- 一旦识别出违反规范的模式，应立即指出并给出修复建议
