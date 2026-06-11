# Pipeline 与事务规范

## Pipeline 定位

Pipeline 负责可重试的后台处理流程，不属于协议适配层。

典型流程：

```text
L0 capture -> L1 extraction -> L1 dedup -> L2 consolidation -> L3 profile update
```

## 基本要求

- 每个 pipeline step 必须可以重复执行。
- 每个 step 必须有清晰输入和输出 schema。
- 写入前必须确定幂等键。
- 长任务必须记录进度，避免失败后从头不可控重跑。
- LLM 调用结果必须记录版本信息和来源 ID。

## 事务边界

Repository 层禁止 `commit()` 和 `rollback()`。

允许的事务边界：

- 单个 MCP/HTTP 请求：由 session context 自动提交或回滚。
- 单个 pipeline step：由 step runner 控制事务。
- 批处理任务：允许按 batch 显式提交，但必须封装在统一 runner 中。

禁止：

- 在 repository 内部提交事务。
- 在 service 中间随意提交，破坏调用方原子性。
- 一个事务同时包住大量 LLM 调用和数据库写入。

## LLM 调用与事务

LLM 调用不应长时间占用数据库事务。

推荐流程：

1. 读取待处理数据并提交或释放事务。
2. 调用 LLM 或外部服务。
3. 重新开启短事务写入结果。
4. 通过幂等键处理重复写入。

## 重试

可重试错误：

- 临时网络失败。
- LLM 限流。
- 数据库序列化冲突。

不可盲目重试：

- schema 校验失败。
- 数据约束冲突且无法通过 upsert 解决。
- 无来源证据的派生结果。

## 状态记录

重要 pipeline 应记录：

- `job_id`
- `step`
- `status`
- `attempt_count`
- `started_at`
- `finished_at`
- `error_message`
- `input_hash`

没有状态表时，至少应在日志中输出这些字段。
