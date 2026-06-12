# L1 到 L2 DB-Native 设计

本文描述 `mcp-memory` 中 L1->L2 的目标设计。设计参考 `yuanxi-memory`，但明确采用 DB-Native 模式：不让 LLM 操作文件，不维护 `scene_blocks/*.md` 文件系统格式，L2 场景直接写入 PostgreSQL 的 `memory_items(layer = 2)`。

## 参考范围

主要参考文件：

- `/Users/xuenai/Code/yuanxi-memory/src/utils/pipeline-factory.ts`
  - `createL2DbRunner`
  - `buildDbL2Prompt`
  - `chooseSceneTarget`
- `/Users/xuenai/Code/yuanxi-memory/src/utils/stateful-pipeline-manager.ts`
  - `advanceL2TimerAfterL1`
  - `armL2MaxInterval`
- `/Users/xuenai/Code/yuanxi-memory/src/services/pipeline-worker.ts`
  - L1 完成后推进 L2 timer
  - L2 完成后级联 L3
  - 分布式锁、重试、死信队列设计
- `/Users/xuenai/Code/yuanxi-memory/src/services/timer-scanner.ts`
  - timer 到期后入队 L2 task
- `/Users/xuenai/Code/yuanxi-memory/src/core/scene/scene-format.ts`
  - L2 Markdown body 的 META 结构
- `/Users/xuenai/Code/yuanxi-memory/src/core/scene/scene-extractor.ts`
  - 文件工具版 SceneExtractor 的场景合并思想
- `/Users/xuenai/Code/yuanxi-memory/src/core/prompts/scene-extraction.ts`
  - 场景整合 prompt 的核心规则
- `/Users/xuenai/Code/yuanxi-memory/src/config.ts`
  - `persona.maxScenes`
  - `pipeline.l2DelayAfterL1Seconds`
  - `pipeline.l2MinIntervalSeconds`
  - `pipeline.l2MaxIntervalSeconds`
  - `pipeline.sessionActiveWindowHours`
- `/Users/xuenai/Code/yuanxi-memory/src/core/types.ts`
  - `LLMRunner`
  - `RuntimeContext`
- `/Users/xuenai/Code/yuanxi-memory/src/core/store/types.ts`
  - `ProfileRecord`
  - `ProfileSyncRecord`
  - L1 query row
- `/Users/xuenai/Code/yuanxi-memory/src/core/state/types.ts`
  - `PipelineSessionState`
  - `TaskPayload`
  - timer / queue / lock 抽象

## 不采用的内容

当前阶段不采用这些能力：

- 不使用 LLM 文件工具。
- 不创建、读取、编辑 `scene_blocks/*.md`。
- 不维护本地 `scene_index` 文件。
- 不做本地备份目录。
- 不实现 Redis Stream worker、分布式锁和 timer scanner 的完整形态。

这些属于 `yuanxi-memory` 的文件系统或分布式服务形态。`mcp-memory` 当前目标是本地单服务 + PostgreSQL DB-Native 版本。

## L2 的定义

L2 是对一批 L1 原子记忆的场景级整合结果。

L1 是碎片化事实：

```text
用户喜欢 X
用户计划 Y
用户在某时间做了 Z
```

L2 是场景叙事文档：

```text
某个稳定场景下，用户是谁、在做什么、有什么偏好、有什么隐性信号、事情如何演变。
```

L2 不应该是 L1 的简单列表，而应该是经过压缩、归纳、合并后的 Markdown 场景文档。

## DB-Native 存储模型

L2 直接复用 `memory_items` 表：

```text
layer = 2
memory_type = "scene_block"
content = L2 Markdown body
scene_name = 场景名
source_session_key = 来源 session
source_conversation_id = 来源 conversation/session
metadata = L2 结构化信息
```

建议 L2 `memory_id`：

```text
l2_ + sha256(user_id + "\0" + scene_filename)
```

其中 `scene_filename` 是逻辑文件名，不是真实文件路径，例如：

```text
技术架构与工程实践.md
日常生活-健康管理.md
```

在 DB-Native 模式中，`filename` 只作为逻辑标识写入 metadata，不对应真实文件。

## L2 Markdown 格式

参考 `yuanxi-memory` 的 scene block META 格式，L2 content 应包含 META 头：

```markdown
-----META-START-----
created: 2026-06-12T04:00:00.000Z
updated: 2026-06-12T04:10:00.000Z
summary: 30-60 字场景摘要
heat: 1
-----META-END-----

## 用户基础信息

## 用户核心特征

## 用户偏好

## 隐性信号

## 核心叙事

## 演变轨迹

## 待确认/矛盾点
```

DB-Native 版本仍保留这个 Markdown body，原因：

- L3 可以直接消费 L2 Markdown。
- recall 时可以作为稳定 system context。
- META 方便解析摘要、热度、更新时间。
- 和 `yuanxi-memory` 的 L2/L3 语义保持兼容。

但 META 中的信息也建议同步拆入 `metadata`：

```json
{
  "filename": "技术架构与工程实践.md",
  "summary": "用户围绕 mcp-memory 进行记忆系统设计与实现",
  "heat": 3,
  "version": 2,
  "source_l1_ids": ["l1_xxx", "l1_yyy"],
  "source_session_key": "grpc:user:conversation",
  "latest_l1_updated_at": "2026-06-12T04:10:00+08:00",
  "generator_version": "l2_db_v1"
}
```

## L1->L2 调度策略

参考 `yuanxi-memory`：

```text
L1 完成
  -> 标记 l2_pending_l1_count
  -> 推进 L2 timer
  -> L2 timer 到期
  -> 执行 L2
  -> L2 完成后设置下一次 maxInterval timer
  -> 后续可级联 L3
```

在 `mcp-memory` 当前单进程形态中，可以先这样做：

```text
L0->L1 pipeline 完成
  -> PipelineScheduler.advance_l2_after_l1(user_id, source_session_key)
  -> 计算 desired_time = max(now + l2DelayAfterL1Seconds, last_l2_run + l2MinIntervalSeconds)
  -> 设置 in-process L2 timer
  -> timer 到期后 run_l2(user_id, source_session_key)
  -> L2 完成后设置下一次 l2MaxIntervalSeconds timer
```

配置来自：

```yaml
memory:
  persona:
    maxScenes: 15

  pipeline:
    l2DelayAfterL1Seconds: 90
    l2MinIntervalSeconds: 900
    l2MaxIntervalSeconds: 3600
```

### 为什么要 delay

`l2DelayAfterL1Seconds` 的作用是避免 L1 刚写完就立刻做 L2：

- 让同一段对话的多个 L1 批次有机会合并。
- 避免频繁调用 L2 LLM。
- 给 dedup、embedding、事务提交留出缓冲。

### 为什么要 min interval

`l2MinIntervalSeconds` 用于限制同一 session 的 L2 运行频率。

如果 L1 很频繁完成，L2 不应该每次都立刻跑。

### 为什么要 max interval

`l2MaxIntervalSeconds` 是兜底刷新。

即使没有新的 L1 快路径推进，也可以让活跃 session 周期性检查是否需要补跑 L2。

## pipeline_state 扩展建议

当前 `pipeline_state` 已有：

```text
conversation_count
warmup_threshold
last_l1_cursor
last_scene_name
l1_running
```

L1->L2 需要新增：

```text
l2_pending_l1_count       -- L1 完成后待 L2 消费的批次数或标记
last_l2_cursor            -- L2 已消费到的 L1 updated_at 游标
l2_last_extraction_time   -- 最近一次 L2 成功完成时间
l2_running                -- L2 是否正在运行
l2_next_run_at            -- L2 timer 到期时间
```

可选增强字段：

```text
l2_retry_count
l2_last_error
l2_failed_at
```

第一阶段可以只实现基础字段，retry 后续再补。

## L2 执行流程

DB-Native L2 pipeline 建议：

```text
run_l2(user_id, source_session_key)
  -> 读取 pipeline_state.last_l2_cursor
  -> query_l1_for_l2(user_id, source_session_key, updated_after)
  -> 如果没有新增 L1：跳过
  -> 查询已有 L2 scene blocks
  -> choose_scene_target()
  -> build_l2_prompt()
  -> LLM 生成 Markdown body
  -> ensure_scene_markdown_body()
  -> upsert_l2_scene()
  -> 更新 last_l2_cursor / l2_last_extraction_time / l2_pending_l1_count
```

## L1 查询规则

L2 应消费 L1，而不是 L0。

查询条件：

```sql
WHERE layer = 1
  AND status = 'active'
  AND is_deleted = false
  AND user_id = :user_id
  AND source_session_key = :source_session_key
  AND updated_at > :last_l2_cursor
ORDER BY updated_at ASC
LIMIT :limit
```

如果历史数据中 `source_session_key` 为空，可以兼容：

```sql
source_conversation_id = :source_session_key
OR source_session_key = :source_session_key
```

L1 row 需要提供给 LLM：

```json
{
  "id": "l1_xxx",
  "content": "用户偏好...",
  "type": "persona",
  "priority": 80,
  "scene_name": "讨论记忆系统设计",
  "created_at": "...",
  "updated_at": "..."
}
```

## 目标场景选择

参考 `yuanxi-memory` 的 `chooseSceneTarget()`：

1. 优先使用新增 L1 中第一个有效 `scene_name`。
2. 将 `scene_name` 转换成安全逻辑 filename。
3. 如果已有 L2 filename 完全匹配，则更新该 L2。
4. 如果当前只有一个 L2，也可以直接更新它。
5. 否则创建新的 L2 scene。

DB-Native 中建议：

```text
scene_name -> safe_scene_filename(scene_name) -> filename
filename -> stable l2 memory_id
```

filename 规则参考：

- 保留中文、英文、数字、短横线、下划线、点号。
- 空格替换为短横线。
- 去掉括号、斜杠、冒号等路径或文件名不安全字符。
- 必须以 `.md` 结尾。

虽然 DB-Native 不落文件，但 filename 仍作为逻辑 ID 使用，应该保持稳定。

## Prompt 设计

第一阶段 prompt 可以直接照搬 `yuanxi-memory` 的 DB-Native prompt，也就是：

```text
/Users/xuenai/Code/yuanxi-memory/src/utils/pipeline-factory.ts
  -> buildDbL2Prompt()
```

这里的“直接照搬”指复制 `buildDbL2Prompt()` 的 system prompt 和 user prompt 语义，而不是复制文件工具版 prompt。

不要直接复制：

```text
/Users/xuenai/Code/yuanxi-memory/src/core/prompts/scene-extraction.ts
```

原因是 `scene-extraction.ts` 面向文件工具版 SceneExtractor，里面包含 `read`、`write`、`edit`、`scene_blocks/*.md`、文件删除标记等要求；这些不适合 `mcp-memory` 的 DB-Native 模式。

DB-Native prompt 的核心要求如下。

System prompt 职责：

```text
你是 L2 场景记忆整合器。
你会把新增 L1 记忆整合成一个可直接入库的 Markdown 场景文档。
只输出最终 Markdown body。
不要输出 JSON。
不要描述文件操作。
不要包裹代码块。
必须保留或生成 META 头。
```

User prompt 输入：

```text
当前时间
目标逻辑文件名
场景数量上限
目标场景当前内容
已有场景参考
新增 L1 记忆 JSON
```

输出要求：

- 使用新增记忆的主导语言。
- 内容是连贯场景叙事。
- 不把 L1 简单堆成流水账。
- 如果已有 target 内容，基于它重写整合。
- 如果没有 target 内容，生成新场景。
- 控制在 1500 字以内。
- 不写数据库、路径、系统实现细节。

实现时建议新增：

```text
src/mcp_memory/prompts/l2_scene.py
src/mcp_memory/prompts/modules/l2_scene_system.md
src/mcp_memory/prompts/modules/l2_scene_user.md
```

其中 `l2_scene_system.md` 和 `l2_scene_user.md` 的内容直接从 `yuanxi-memory` 的 `buildDbL2Prompt()` 拆出来，只做 Python `.format()` 所需的变量占位调整。

## ensure_scene_markdown_body

LLM 可能漏掉 META 头。工程侧需要兜底：

```text
if body 缺少 META:
  prepend META
else:
  校正 updated
  校正 summary/heat 缺失项
```

兜底 META：

```markdown
-----META-START-----
created: 原 created 或 now
updated: now
summary: 从 L1 内容截断生成
heat: 1 或 existing heat + 1
-----META-END-----
```

第一阶段可以简单实现：

- 缺 META 时 prepend。
- 有 META 时信任 LLM 输出。
- 后续再做严格 parse 和字段修复。

## Repository 设计

建议在 `MemoryItemRepository` 增加：

```python
query_l1_for_l2(
    user_id: str,
    source_session_key: str,
    updated_after: datetime | None,
    limit: int,
) -> list[L1ForL2Row]

query_l2_scenes(
    user_id: str,
    limit: int,
) -> list[L2SceneRow]

upsert_l2_scene(
    scene: L2SceneCreate,
) -> None
```

对应 DB：

```text
query_l1_for_l2 -> memory_items(layer=1)
query_l2_scenes -> memory_items(layer=2, memory_type='scene_block')
upsert_l2_scene -> INSERT ... ON CONFLICT(memory_id) DO UPDATE
```

## Service / Pipeline 分层

建议新增：

```text
src/mcp_memory/prompts/l2_scene.py
src/mcp_memory/prompts/modules/l2_scene_system.md
src/mcp_memory/prompts/modules/l2_scene_user.md

src/mcp_memory/services/l2_scene.py
src/mcp_memory/pipelines/l1_to_l2.py
```

职责划分：

```text
prompts/l2_scene.py
  -> 构造 prompt

services/l2_scene.py
  -> 调 LLM
  -> strip markdown fence
  -> ensure META
  -> 生成 L2 scene create object

pipelines/l1_to_l2.py
  -> 查询增量 L1
  -> 查询已有 L2
  -> 选择 target scene
  -> 调 service
  -> 写 DB
  -> 返回 latest_cursor
```

调度仍放在：

```text
services/pipeline_scheduler.py
repositories/pipeline_state.py
```

## Scheduler 接入点

当前 L1 完成后在 `PipelineScheduler.run_l1()` 中调用：

```text
mark_l1_complete(...)
```

设计上应在 L1 成功后追加：

```text
advance_l2_after_l1(user_id, source_session_key)
```

行为：

```text
if result.stored_count > 0:
  l2_pending_l1_count += 1
  desired_time = max(now + l2DelayAfterL1Seconds, last_l2_time + l2MinIntervalSeconds)
  设置或提前 L2 timer
```

如果 L1 没有新写入，是否触发 L2：

- 第一阶段建议不触发。
- 如果 L1 被 dedup 全部 skip，也不需要 L2。

L2 timer 到期后：

```text
run_l2(user_id, source_session_key)
```

执行成功后：

```text
l2_pending_l1_count = 0
l2_last_extraction_time = now
last_l2_cursor = latest L1 updated_at
l2_running = false
设置下一次 maxInterval timer
```

## 与 L3 的关系

`yuanxi-memory` 中：

```text
L2 完成 -> enqueue L3
```

当前 `mcp-memory` 第一阶段可以先不实现 L3，但 L2 完成后应保留扩展点：

```text
on_l2_complete()
```

后续 L3 接入时可以在这里触发 persona 生成。

## 当前实现范围

当前已经完成：

1. 扩展 `pipeline_state` L2 字段。
2. 增加 L2 配置读取。
3. 增加 L1 增量查询。
4. 增加 L2 scene 查询与 upsert。
5. 增加 L2 DB-native prompt。
6. 增加 `L1ToL2Pipeline`。
7. L1 完成后设置 L2 timer。
8. L2 timer 到期后执行 L2。
9. L2 写入 `memory_items(layer=2)`。
10. L2 完成后更新 cursor 和 last run time。

当前暂未实现：

- Redis Stream worker。
- 分布式锁。
- dead letter。
- pending task recovery。
- L3 persona。
- 文件工具版 SceneExtractor。
- scene_index 文件。
- 本地 backup。
- `l2MaxIntervalSeconds` 周期性空闲扫描。当前 L2 主要由 L1 成功写入后的 fast path 触发，避免空跑。

## 风险点

### 1. 过度创建 L2 场景

如果 `choose_scene_target` 太简单，可能每个 session 或每个 scene_name 都创建一个 L2。

缓解：

- `persona.maxScenes` 限制数量。
- 场景数接近上限时，prompt 要求优先更新已有场景。
- 后续增加 L2 scene 相似召回。

### 2. L2 content 被 LLM 写坏

风险：

- 没有 META。
- 输出代码块。
- 输出 JSON。
- 输出系统说明。

缓解：

- `strip_markdown_fence()`。
- `ensure_scene_markdown_body()`。
- 后续增加 `parse_scene_meta()` 严格校验。

### 3. cursor 类型选择

`yuanxi-memory` 用 ISO `updatedAfter`。

`mcp-memory` 可以用：

- `last_l2_cursor` 存 ISO 字符串。
- 或 `last_l2_cursor_ms` 存 epoch ms。

建议使用 ISO 字符串或 timestamp 字段，而不是复用 `last_l1_cursor` 的 L0 message timestamp 语义。

### 4. L2 和 L1 并发

如果 L2 运行时新的 L1 又写入：

- L2 本轮只处理 cursor 之前查到的记录。
- 新 L1 留到下一轮。
- `l2_pending_l1_count` 不应被错误清零。

第一阶段单进程可以简化处理；后续多实例需要锁或 lease。

## 文件清单建议

实现时预计新增或修改：

```text
config/local.example.yaml
src/mcp_memory/config.py

src/mcp_memory/models/pipeline_state.py
migrations/versions/<revision>_add_l2_pipeline_state.py

src/mcp_memory/schemas/memory_items.py
src/mcp_memory/repositories/memory_items.py
src/mcp_memory/repositories/pipeline_state.py

src/mcp_memory/prompts/l2_scene.py
src/mcp_memory/prompts/modules/l2_scene_system.md
src/mcp_memory/prompts/modules/l2_scene_user.md

src/mcp_memory/services/l2_scene.py
src/mcp_memory/pipelines/l1_to_l2.py
src/mcp_memory/services/pipeline_scheduler.py

docs/l1-to-l2-design.md
```

## 最终目标链路

```text
L0
  -> L1 extraction
  -> L1 dedup
  -> memory_items(layer=1)
  -> L2 timer
  -> query incremental L1
  -> DB-native scene prompt
  -> memory_items(layer=2, memory_type='scene_block')
```

这条链路完成后，`mcp-memory` 就具备 DB-Native 的 L1->L2 基础能力，后续再接 L2->L3 persona。
