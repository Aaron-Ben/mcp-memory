# L0 到 L1 流程说明

## 当前状态

`mcp-memory` 目前只实现了 L0 保存，还没有实现 L0 -> L1 抽取流程。

当前已实现链路：

```text
mcp-client
  -> gRPC IngestMessages
  -> mcp_memory.grpc.memory_service.MemoryService
  -> mcp_memory.services.l0_memory.L0MemoryService
  -> mcp_memory.repositories.memory_items.MemoryItemRepository.upsert_l0
  -> memory_items(layer = 0)
```

L0 保存当前做的事：

- 校验 `user_id`、`conversation_id`、`messages`。
- 跳过 `tool` / `tool_result` 角色消息。
- 过滤 `<system-reminder>...</system-reminder>` 包裹内容。
- 生成或复用稳定 `memory_id`。
- 写入 `memory_items`，其中 `layer = 0`。
- 在 `metadata` 中记录 `_role`、`_session_key`、`message_ts_ms`、`recorded_at`。

也就是说，当前 `mcp-memory` 还没有：

- L1 抽取器。
- L1 去重逻辑。
- L1 写入 repository。
- 后台 pipeline / worker。
- L0 已处理进度记录。

## yuanxi-memory 参考流程

`yuanxi-memory` 中 L0 -> L1 不是在 gRPC 请求里同步完成，而是异步 pipeline。

核心流程：

```text
gRPC IngestMessages
  -> normalize message
  -> reserveNewMessages 做消息幂等
  -> enqueueCapture
  -> 保存 L0
  -> 调度 L1 pipeline
  -> queryL0ForL1 读取 L0
  -> extractL1Memories 调用 LLM 抽取
  -> batchDedup 做候选召回和冲突判断
  -> writeMemory / upsertL1 写入 L1
```

关键文件：

- `/Users/xuenai/Code/yuanxi-memory/src/grpc/memory-grpc-server.ts`
- `/Users/xuenai/Code/yuanxi-memory/src/core/store/pgsql.ts`
- `/Users/xuenai/Code/yuanxi-memory/src/core/record/l1-extractor.ts`
- `/Users/xuenai/Code/yuanxi-memory/src/core/record/l1-dedup.ts`
- `/Users/xuenai/Code/yuanxi-memory/src/core/record/l1-writer.ts`
- `/Users/xuenai/Code/yuanxi-memory/src/core/prompts/l1-extraction.ts`
- `/Users/xuenai/Code/yuanxi-memory/src/services/pipeline-worker.ts`

### 1. gRPC 接收消息

`IngestMessages` 接收 `user_id`、`conversation_id`、`messages`。

它会做：

- 标准化 `role`、`content`、`timestamp`。
- 过滤 tool 消息。
- 用消息 ID 做幂等保留。
- 只把新增消息放入 capture 队列。

这个阶段只负责“收下消息”，不直接做 L1 抽取。

### 2. L0 写入

`PgsqlMemoryStore.upsertL0()` 将消息写入 `memory_items`：

```text
layer = 0
memory_type = role
content = message_text
source_conversation_id = session_id
source_session_key = session_key
metadata._role = role
metadata._session_key = session_key
metadata.message_ts_ms = message timestamp
metadata.recorded_at = recorded_at
```

写入使用 `ON CONFLICT (memory_id) DO UPDATE`，保证重复消息不会产生重复 L0。

### 3. 查询待抽取 L0

`queryL0ForL1(sessionKey, afterRecordedAtMs, limit)` 读取 L0：

```text
WHERE layer = 0
  AND status = 'active'
  AND is_deleted = false
  AND user_id = resolved_user_id
  AND (source_conversation_id = sessionKey OR source_session_key = sessionKey)
  AND message_ts_ms > afterRecordedAtMs
ORDER BY message_ts_ms ASC
LIMIT ...
```

这里的关键点：

- 按时间升序读取，保证 LLM 看到自然对话顺序。
- 用 `afterRecordedAtMs` 做增量抽取。
- 时间优先使用 `metadata.message_ts_ms`，没有则回退到 `created_at`。

### 4. L1 抽取

`extractL1Memories()` 是核心抽取函数。

它做的步骤：

1. 质量过滤：通过 `shouldExtractL1()` 过滤太短、噪声、注入风险等不适合抽取的消息。
2. 切分输入：把消息分成 background 和 new messages。
3. 调用 LLM：使用 `EXTRACT_MEMORIES_SYSTEM_PROMPT` 和 `formatExtractionPrompt()`。
4. 解析 JSON：LLM 返回 scene 数组，每个 scene 下有 memories。
5. 标准化 memory type：只允许 `persona`、`episodic`、`instruction`。
6. 限制单次抽取数量：`maxMemoriesPerSession`。
7. 给每条候选 L1 分配临时 `record_id`。

### LLM 与 Embedding 接入方式

`mcp-client` 和 `yuanxi-memory` 的边界不同：

- `mcp-client` 自己使用 `BaseChatModel` / `BaseEmbeddingModel`，模型配置来自 Redis，底层是 OpenAI-compatible API。
- `yuanxi-memory` 的 core 不直接依赖某个宿主项目，而是通过 `LLMRunner` 和 `EmbeddingService` 这两个抽象使用模型能力。
- `yuanxi-memory` 的 standalone adapter 也是 OpenAI-compatible API；openclaw adapter 则把调用转交给宿主运行器。

因此 `mcp-memory` 不应直接 import `mcp-client` 的 Redis 模型配置逻辑。更合理的方式是：

```text
L0ToL1Pipeline
  -> L1Extractor
  -> LLMRunner 抽象
  -> OpenAI-compatible adapter

L1MemoryService
  -> EmbeddingProvider 抽象
  -> OpenAI-compatible adapter
```

当前实现中，具体模型通过 `config/local.yaml` 配置：

```text
llm.apiKey
llm.baseUrl
llm.model
llm.timeoutMs
llm.maxTokens

memory.embedding.enabled
memory.embedding.apiKey
memory.embedding.baseUrl
memory.embedding.model
memory.embedding.dimensions
memory.embedding.timeoutMs
memory.embedding.sendDimensions
memory.embedding.maxInputChars
```

LLM 预期输出结构：

```json
[
  {
    "scene_name": "当前情境名称",
    "message_ids": ["message_id_1"],
    "memories": [
      {
        "content": "完整、独立的记忆陈述",
        "type": "persona",
        "priority": 80,
        "source_message_ids": ["message_id_1"],
        "metadata": {}
      }
    ]
  }
]
```

### 5. L1 去重与合并

`batchDedup()` 负责判断新抽取的 L1 如何落库。

处理方式：

- 先通过向量检索或全文检索召回相似 L1。
- 如果没有候选，直接 `store`。
- 如果有候选，调用 LLM 做冲突判断。

去重决策有四种：

| action | 含义 |
|--------|------|
| `store` | 作为新 L1 写入 |
| `update` | 用新内容更新已有 L1 |
| `merge` | 合并多条已有 L1 和新 L1 |
| `skip` | 认为无价值或重复，不写入 |

### 6. L1 写入

`writeMemory()` 根据去重决策生成最终 `MemoryRecord`，然后写入存储。

在 PGSQL 路径中，最终通过 `upsertL1()` 写入 `memory_items`：

```text
layer = 1
memory_type = persona | episodic | instruction
content = 抽取后的原子记忆
priority = LLM 输出或合并后的优先级
scene_name = 情境名称
source_conversation_id = session_id
source_session_key = session_key
metadata = 原 metadata + _session_key
embedding = 可选向量
status = active
```

更新/合并时，会对被替换的旧 L1 做软删除：

```text
status = archived
is_deleted = true
deleted_at = now
```

## mcp-memory 后续建议设计

`mcp-memory` 应保持 PGSQL 单表模型：L0/L1/L2/L3 都写入 `memory_items`，用 `layer` 区分。

建议新增目录：

```text
src/mcp_memory/
├── pipelines/
│   ├── __init__.py
│   └── l0_to_l1.py
├── extractors/
│   ├── __init__.py
│   └── l1_extractor.py
├── prompts/
│   ├── __init__.py
│   ├── _loader.py
│   ├── l1_extraction.py
│   └── modules/
│       ├── l1_extraction_system.md
│       └── l1_extraction_user.md
└── repositories/
    └── memory_items.py
```

建议调用链：

```text
MemoryService.IngestMessages
  -> L0MemoryService.save_message
  -> enqueue_l0_to_l1_job
  -> L0ToL1Pipeline.run(job)
  -> MemoryItemRepository.query_l0_for_l1
  -> L1Extractor.extract
  -> L1DedupService.dedup
  -> MemoryItemRepository.upsert_l1
```

### 建议的 pipeline 边界

不要在 gRPC 请求里同步调用 LLM。

原因：

- `mcp-client` 的 memory ingest 是 fire-and-forget，失败不应影响主流程。
- LLM 抽取耗时长，可能超过 gRPC timeout。
- L0 保存和 L1 抽取应可独立重试。
- LLM 调用不应长时间占用数据库事务。

建议：

1. gRPC 请求只保存 L0，并记录待处理 job。
2. 后台 worker 扫描 pending job。
3. worker 查询 L0，释放数据库事务。
4. worker 调用 LLM 抽取 L1。
5. worker 开短事务写入 L1 和处理进度。

### 建议的 L1 metadata

L1 必须保留来源，建议 metadata 至少包含：

```json
{
  "source_memory_ids": ["l0_message_id_1", "l0_message_id_2"],
  "source_message_ids": ["client_message_id_1"],
  "confidence": 0.8,
  "extractor_version": "l1_v1",
  "extracted_at": "2026-06-12T00:00:00+08:00",
  "_session_key": "grpc:user:conversation"
}
```

其中：

- `source_memory_ids`: 对应 `memory_items.memory_id`，用于 lineage。
- `source_message_ids`: 对应原始消息 ID，便于排查。
- `extractor_version`: 用于后续重新抽取和兼容迁移。
- `confidence`: 置信度，后续召回和 L2/L3 晋升会用到。

### 建议的 L1 memory_id

不要使用纯随机 ID。

建议用稳定派生：

```text
l1_ + sha256(user_id + source_l0_ids + extractor_version + normalized_content)
```

这样 pipeline 重试时不会重复写入同一条 L1。

### 建议的第一阶段实现范围

第一阶段可以先做最小闭环：

1. `query_l0_for_l1(user_id, source_session_key, after_timestamp_ms, limit)`。
2. `L1Extractor` 使用固定 prompt 调 LLM。
3. `upsert_l1()` 写入 `memory_items(layer=1)`，接口第一版就应支持可选 `embedding`。
4. 正常路径在写 L1 前生成 embedding，用于后续召回和去重；embedding 失败时允许降级写入 `embedding = NULL`。
5. 第一阶段可暂不做复杂 LLM dedup，但不要把 `upsert_l1()` 设计成无法接收 embedding。
6. 记录 `metadata.source_memory_ids` 和 `metadata.extractor_version`。

第二阶段再补：

- 相似 L1 召回。
- LLM dedup。
- pipeline job 状态表或 pending job 记录。
- L1 -> L2 聚合触发。

## 和当前代码的差距

当前已有：

- `memory_items` 表模型。
- L0 schema。
- L0 repository。
- L0 service。
- gRPC ingest。

当前缺失：

- L1 schema。
- `upsert_l1()`。
- `query_l0_for_l1()`。
- L1 prompt。
- L1 extractor。
- L1 dedup。
- L0->L1 pipeline。
- 后台 worker 或定时扫描。

因此，下一步不应直接写 L2/L3，而应先补齐 L0->L1 的最小闭环。
