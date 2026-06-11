# 可观测性规范

## 日志

日志必须能回答：

- 哪个用户或租户触发了操作。
- 处理的是哪个 conversation/session。
- 当前处于哪个 layer 或 pipeline step。
- 写入或召回了哪些 memory_id。
- 失败原因是否可重试。

推荐字段：

- `user_id`
- `source_conversation_id`
- `source_session_key`
- `memory_id`
- `layer`
- `job_id`
- `step`
- `attempt`
- `duration_ms`

## 指标

核心指标：

- L0 capture 数量。
- L1 抽取数量和失败率。
- L2 聚合数量和失败率。
- L3 更新数量。
- recall 延迟。
- vector search 延迟。
- 每次 recall 返回记忆数量。

## Trace

跨 L0->L3 的 pipeline 应保留 trace id 或 job id。

要求：

- 一个用户请求触发的所有后台步骤可串联。
- LLM 调用、数据库写入、向量检索应能分段计时。

## 审计

派生记忆必须能回溯来源。

至少保留：

- 来源 memory id。
- 抽取器或聚合器版本。
- 生成时间。
- 置信度。
- 更新前后的版本关系。
