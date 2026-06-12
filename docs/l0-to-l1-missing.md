# L0 到 L1 未实现项

本文只记录 `mcp-memory` 当前 L0->L1 相对完整实现仍缺失的能力，不重复描述已经完成的主链路。

## 当前已具备的基础链路

当前项目已经具备最小 L0->L1 闭环：

```text
gRPC IngestMessages
  -> 保存 L0
  -> pipeline_state 累计会话轮数
  -> 阈值触发或 idle 触发
  -> 查询待处理 L0
  -> L1 质量过滤
  -> LLM 情境切分与 L1 抽取
  -> 可选 L1 dedup
  -> 写入 memory_items(layer = 1)
  -> 更新 last_l1_cursor / last_scene_name
```

也就是说，当前缺失项不是“完全不能跑”，而是可靠性、召回质量、数据语义和任务调度完整度还不够。

## P1：失败重试与 flush

### L1 retry_count

当前失败后只释放 `l1_running`，没有持久化 retry 状态。

缺少字段或等价状态：

```text
l1_retry_count
last_l1_error
last_l1_failed_at
next_retry_at
max_retry
```

需要补的行为：

- L1 失败后记录失败原因。
- 根据 retry 次数决定是否重试。
- 支持指数退避或固定延迟重试。
- 超过最大重试次数后进入可观测的失败状态，而不是静默丢失。

### idle 失败重试

当前 idle timer 触发失败时只记录日志。

缺少：

- idle 触发失败后的重新调度。
- idle 失败次数记录。
- idle 失败超过阈值后的告警或状态标记。

### shutdown flush pending session

当前 shutdown 会等待正在运行的后台任务，并取消 idle timer。

缺少：

- 服务退出前扫描 `conversation_count > 0` 的 session。
- 对 pending session 做最后一次 L1 flush。
- flush 失败时记录可恢复状态。

这个能力用于减少服务重启或手动停止时的 L0 堆积和漏处理。

## P2：stale running 恢复

当前 `pipeline_state.l1_running` 用于避免同一个 session 并发跑多个 L1。

问题是：如果进程在 `l1_running = true` 时崩溃，状态可能永久卡住。

缺少：

- `l1_started_at` 或 task lease 时间。
- 定期扫描超时 running 状态。
- 超时后释放 `l1_running` 并允许重新触发。
- 多实例下的 lease owner 或 worker id。

## P3：dedup 候选召回完整度

当前 dedup 已实现：

```text
新 L1 embedding
  -> 向量召回已有 L1
  -> LLM 判断 store / skip / update / merge
```

缺少：

- FTS / BM25 fallback。
- 相似度阈值配置。
- topK 配置化。
- 多阶段候选过滤。
- 候选召回失败时的明确降级策略和日志。

当前如果 embedding 召回没有命中，系统会直接 `store`，这可以工作，但不等价于完整 dedup。

## P4：dedup 合并语义字段

`yuanxi-memory` 的 dedup prompt 中包含 `merged_timestamps`，用于保留合并前后记忆的时间线。

当前 `mcp-memory` 还没有在 schema 和写入逻辑中消费该字段。

缺少：

- `L1MemoryDedupDecision.merged_timestamps`。
- 从旧 L1 metadata 中读取 timestamps。
- merge / update 后把时间戳并集写回 metadata。
- 对 episodic 记忆的时间线查询支持。

## P5：L1 extraction 输出后的质量校验

当前已有 `should_extract_l1`，它是在 LLM 前过滤 L0 输入。

还缺少 LLM 输出后的二次质量校验：

- 过滤过短的 L1 content。
- 过滤没有独立语义的 L1。
- 校验 `source_message_ids` 是否真的来自本批新消息。
- 校验 `priority` 是否在合理区间。
- 校验 `metadata` 中时间字段是否是合法 ISO 8601。
- 对 prompt injection 类输出做保护。

目前主要依赖 prompt 和 Pydantic 基础解析，语义校验还不完整。

## P6：L1 时间 metadata 的结构化使用

当前 prompt 允许 episodic 输出：

```json
{
  "activity_start_time": "...",
  "activity_end_time": "..."
}
```

这些字段目前只会进入 `metadata`，没有专门索引或查询逻辑。

缺少：

- 时间字段规范化。
- 时间字段校验。
- 根据 activity time 做排序或召回。
- 后续 L2/L3 聚合时使用该时间范围。

## P7：capture queue 与任务持久化

当前保存 L0 后直接通知 in-process scheduler。

`yuanxi-memory` 中还有类似：

```text
reserveNewMessages
enqueueCapture
pipeline worker
```

当前缺少：

- 独立 capture queue。
- pending job 表。
- job 状态机。
- job 级别重试。
- 服务重启后的 job 恢复。

本地开发阶段可以先用当前 in-process scheduler，但生产形态需要持久化任务队列。

## P8：多实例并发与分布式 worker

当前设计更偏单进程服务。

缺少：

- 多实例下的任务抢占协议。
- worker lease。
- 同一个 session 的并发互斥。
- stale lease 回收。
- worker 心跳。

如果只在本地或单实例运行，这不是立刻阻塞项；如果之后要部署为服务，这是必须补的。

## P9：可观测性与调试能力

当前日志已经能看到：

```text
queried
processed
qualified
extracted
stored
dedup action count
```

还缺少：

- 每条 L0 被过滤的原因。
- LLM 原始输出的安全采样或 debug 存储。
- 每条 L1 dedup decision 明细。
- LLM 调用耗时。
- token 用量。
- embedding 调用耗时和失败率。
- L1 失败原因分类。

这些能力不会改变主流程，但会显著降低排查 L1 质量问题的成本。

## 建议实现顺序

优先级建议：

```text
P1 失败重试与 shutdown flush
P2 stale running 恢复
P3 dedup FTS fallback 和阈值配置
P4 dedup merged_timestamps
P5 LLM 输出后质量校验
P6 时间 metadata 结构化使用
P7 capture queue / pending job
P8 多实例 worker
P9 可观测性增强
```

短期最应该先做的是 P1 和 P2。它们属于可靠性能力，优先级高于继续优化 prompt 或 L2/L3。

## hy-memory演化链
当前的L0->L1，对于发现重复的，相似度高的L1，直接是替换掉，status标记archived，is_deleted标记true，这里未来可以去参考hy-memory的演化链。