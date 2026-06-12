# L2 到 L3 DB-Native 设计

本文描述 `mcp-memory` 中 L2->L3 的目标设计。设计参考 `yuanxi-memory` 的 persona 生成链路，但继续采用 DB-Native 模式：不让 LLM 操作文件，不维护 `persona.md` 或 `scene_index.json` 文件，L3 用户画像直接写入 PostgreSQL 的 `memory_items(layer = 3)`。

## 参考范围

主要参考文件：

- `/Users/xuenai/Code/yuanxi-memory/src/utils/pipeline-manager.ts`
  - L2 完成后触发 L3。
  - L3 使用全局串行队列。
  - `l3Running` + `l3Pending` 用于避免并发生成，并在运行期间合并重复触发。
- `/Users/xuenai/Code/yuanxi-memory/src/utils/pipeline-factory.ts`
  - `createL3Runner`
  - `createL3DbRunner`
  - `buildDbL3Prompt`
  - `stripMarkdownFence`
- `/Users/xuenai/Code/yuanxi-memory/src/core/persona/persona-generator.ts`
  - 读取已有 persona。
  - 找出自上次 persona 更新后变化的 L2 场景。
  - 生成或增量更新 persona。
  - 追加 scene navigation。
- `/Users/xuenai/Code/yuanxi-memory/src/core/persona/persona-trigger.ts`
  - 判断是否需要生成 persona。
  - 支持主动请求、冷启动、恢复、首次 scene、阈值触发。
- `/Users/xuenai/Code/yuanxi-memory/src/core/prompts/persona-generation.ts`
  - Persona 生成的核心 prompt。
  - 四层扫描模型：基础锚点、兴趣图谱、交互协议、认知内核。
- `/Users/xuenai/Code/yuanxi-memory/src/core/scene/scene-index.ts`
  - scene index 的结构：filename、summary、heat、created、updated。
  - DB-Native 模式不落文件，但需要保留等价的索引语义。
- `/Users/xuenai/Code/yuanxi-memory/src/core/scene/scene-navigation.ts`
  - `generateDbSceneNavigation`
  - `stripSceneNavigation`
  - DB-Native persona 不使用文件路径，navigation 只作为 memory store 中的场景索引提示。

## 不采用的内容

当前阶段不采用这些能力：

- 不使用 LLM 文件工具。
- 不创建或编辑 `persona.md`。
- 不创建或扫描 `scene_blocks/*.md`。
- 不维护 `.metadata/scene_index.json` 文件。
- 不维护本地 backup。
- 不实现 COS/local file sync。
- 不实现分布式 Redis 队列、分布式锁和 dead letter。

这些属于 `yuanxi-memory` 的文件系统或分布式运行形态。`mcp-memory` 当前目标是本地单服务 + PostgreSQL DB-Native 版本。

## L3 的定义

L3 是用户级 persona，是对所有 L2 场景记忆的长期画像整合。

L2 是场景级记忆：

```text
用户近期围绕某个项目、兴趣、习惯或关系形成的一段场景叙事。
```

L3 是跨场景用户画像：

```text
用户是谁、长期偏好是什么、如何沟通、如何决策、最近如何变化、有哪些稳定可复用的个性化规则。
```

L3 不应该简单罗列 L2，也不应该把所有场景全部塞进正文。L3 应该压缩、归纳、校正、连接不同场景之间的长期模式。

## DB-Native 存储模型

L3 直接复用 `memory_items` 表：

```text
layer = 3
memory_type = "persona"
content = persona Markdown body
scene_name = "persona"
source_conversation_id = ""
source_session_key = ""
metadata = L3 结构化信息
```

建议 L3 `memory_id` 稳定为：

```text
l3_ + sha256(user_id + "\0" + "persona.md")
```

或更简单地使用：

```text
l3_{user_id_hash}
```

关键是同一用户只有一个 active L3 persona。后续更新应 `ON CONFLICT(memory_id) DO UPDATE`，不要为同一用户生成多个 active L3。

建议 metadata：

```json
{
  "filename": "persona.md",
  "summary": "用户长期画像摘要",
  "generator_version": "l3_db_v1",
  "mode": "first|incremental",
  "trigger_reason": "cold_start|first_scene|threshold|manual|recovery|l2_complete",
  "source_l2_ids": ["l2_xxx", "l2_yyy"],
  "source_l2_filenames": ["工程实践.md", "音乐兴趣.md"],
  "scene_count": 8,
  "changed_scene_count": 2,
  "last_scene_updated_at": "2026-06-12T12:00:00+08:00",
  "navigation_appended": true
}
```

## L3 状态模型

当前 `pipeline_state` 是 session 级别：

```text
PRIMARY KEY (user_id, source_session_key)
```

L3 是 user 级别，跨 session 聚合所有 L2。因此本阶段不把 L3 状态塞进普通 session 的 `pipeline_state`，也不新增 `persona_state` 表。

不把 L3 状态放进 `pipeline_state` 的原因：

- L3 不属于某个单独 `source_session_key`。
- 多个 session 同时完成 L2 时，需要按 user 去重和串行化。
- `pipeline_state` 的 L1/L2 cursor 是 session 维度，L3 cursor 应该是 user 维度。

本阶段采用更轻量的做法：

```text
L3 是否需要增量更新：
  -> 读取当前用户 active L3 persona 的 updated_at
  -> 查询 updated_at > persona.updated_at 的 active L2 scenes
  -> 如果没有 L3，则首次生成读取全部 L2 scenes

L3 并发控制：
  -> PipelineScheduler 内存中按 user_id 维护 _l3_tasks
  -> 如果同一 user_id 的 L3 正在运行，则记录 pending user
  -> 当前 L3 完成后，如果 user 仍 pending，再跑一轮
```

这个方案的代价：

```text
进程重启后不会恢复内存 pending 状态。
但 L3 可以通过 L2.updated_at > L3.updated_at 重新判断是否需要更新，因此不会永久丢失可生成的数据。
```

后续如果需要跨进程、失败重试、定时触发或恢复 pending 状态，再考虑新增用户级状态表。

## L2->L3 触发策略

参考 `yuanxi-memory`：

```text
L2 完成
  -> triggerL3()
  -> 如果 L3 未运行，进入 L3 队列
  -> 如果 L3 正在运行，只标记 l3Pending=true
  -> 当前 L3 完成后，如果 pending=true，再跑一次
```

在 `mcp-memory` 中建议：

```text
PipelineScheduler.run_l2 成功
  -> mark_l2_complete(...)
  -> notify_l3_after_l2(user_id)
  -> PipelineScheduler 按 user_id 做内存级 running/pending 去重
  -> 后台执行 L2ToL3Pipeline
```

触发粒度：

- L2 是 session 级别。
- L3 是 user 级别。
- 任意 session 的 L2 成功写入后，都可以通知同一 user 的 L3。

第一阶段建议只在 L2 `stored_count > 0` 时触发 L3。如果 L2 skipped 或没有变化，不触发。

## PersonaTrigger 等价规则

`yuanxi-memory` 的 `PersonaTrigger` 有 5 类触发条件：

1. 主动请求：checkpoint 中有 `request_persona_update`。
2. 冷启动：已有 scene，但还没有 persona。
3. 恢复：persona 曾经生成过，但正文丢失或为空。
4. 首次 scene：第一个 scene block 生成完成。
5. 阈值：距离上次 persona 后的 memory/scene 变化数量达到阈值。

DB-Native 模式中可以映射为：

```text
manual:
  外部 API 或管理命令显式要求更新 persona。

cold_start:
  memory_items 存在 layer=2 active 场景，但不存在 layer=3 active persona。

recovery:
  存在 layer=3 active persona，但 content 为空或只剩 navigation。

first_scene:
  active L2 场景数为 1，且 persona 尚未生成。

threshold:
  自 last_l3_cursor 之后更新的 L2 场景数 >= memory.persona.triggerEveryN。
```

当前 `config/local.yaml` 尚未定义 `triggerEveryN` 时，建议新增：

```yaml
memory:
  persona:
    enabled: true
    maxScenes: 15
    triggerEveryN: 50
    maxLength: 2000
```

如果本地开发阶段想快速验证 L2->L3，可以临时设为 `1`，即每次 L2 有变化就尝试 L3；稳定后建议调回更大的值以降低 LLM 调用频率。

## L3 查询规则

L3 消费 L2，而不是 L1。

查询所有 active L2：

```sql
SELECT *
FROM memory_items
WHERE layer = 2
  AND memory_type = 'scene_block'
  AND status = 'active'
  AND is_deleted = false
  AND user_id = :user_id
ORDER BY updated_at DESC
LIMIT :max_scenes;
```

查询变化 L2：

```sql
SELECT *
FROM memory_items
WHERE layer = 2
  AND memory_type = 'scene_block'
  AND status = 'active'
  AND is_deleted = false
  AND user_id = :user_id
  AND updated_at > :last_l3_cursor
ORDER BY updated_at ASC
LIMIT :limit;
```

增量模式中：

- `changed_scenes` 用于提示词重点分析。
- `all_scenes` 用于 scene navigation 和必要的全局参考。
- 如果没有现有 persona，则用全部 L2 进行首次生成。
- 如果已有 persona，则只把变化 L2 作为重点输入，同时把现有 persona 一并提供给 LLM。

## Scene Index 等价设计

文件系统版本的 scene index 存储：

```json
[
  {
    "filename": "xxx.md",
    "summary": "...",
    "heat": 3,
    "created": "...",
    "updated": "..."
  }
]
```

DB-Native 不需要 `scene_index.json`，但需要从 `memory_items(layer=2)` 动态构造等价索引。

建议从 L2 metadata + content META 中读取：

```text
filename -> metadata.filename
summary  -> metadata.summary 或 L2 META summary
heat     -> metadata.heat 或 L2 META heat
created  -> created_at 或 L2 META created
updated  -> updated_at 或 L2 META updated
```

建议新增 repository 方法：

```python
query_l2_scene_index(
    db,
    user_id: str,
    limit: int,
) -> list[L2SceneIndexEntry]
```

## Scene Navigation

参考 `generateDbSceneNavigation()`，DB-Native navigation 不应该包含文件路径。

建议追加到 persona content 末尾：

```markdown
## Scene Navigation (Memory Store Index)
*The following scene profiles are indexed in the memory store for this user. Use the names as retrieval hints; do not treat them as files or paths.*

### 工程实践
Summary: 用户长期围绕 mcp-memory 进行 DB-native 记忆系统开发 | Updated: 2026-06-12T12:00:00+08:00 | Heat: 5

### 音乐兴趣
Summary: 用户近期正在了解 City Pop 音乐风格及其时代背景 | Updated: 2026-06-12T11:42:00+08:00 | Heat: 1
```

工程侧需要提供：

```python
strip_scene_navigation(persona_content: str) -> str
generate_db_scene_navigation(scenes: list[L2SceneRow]) -> str
```

注意：

- LLM prompt 中要求“不要添加 scene navigation”。
- navigation 由工程侧追加。
- 读取已有 persona 时，应先 strip navigation，再提供给 LLM。

## Prompt 设计

第一阶段建议优先采用 `yuanxi-memory` 的 DB-native prompt：

```text
/Users/xuenai/Code/yuanxi-memory/src/utils/pipeline-factory.ts
  -> buildDbL3Prompt()
```

但这个 prompt 相对简化，适合作为第一版。

如果希望更接近完整 persona 质量，应参考：

```text
/Users/xuenai/Code/yuanxi-memory/src/core/prompts/persona-generation.ts
```

需要注意：`persona-generation.ts` 是文件工具版 prompt，包含 `write/edit persona.md`、只能操作文件等要求。DB-Native 模式不能直接照抄文件操作约束，应保留其中的 persona 思维框架和输出模板，删除文件工具要求。

DB-Native L3 system prompt 建议：

```text
你是 L3 用户画像生成器。
你会基于 L2 场景记忆生成一个可直接入库的 persona Markdown body。

只输出最终 Markdown body。
不要输出 JSON。
不要调用或描述文件操作。
不要包裹代码块。
不要添加 Scene Navigation，工程会自动追加。

只基于提供的 L2 场景证据，不要凭空编造。
输出语言跟随场景内容主导语言。
控制在 2000 字以内。
内容应服务于 Agent 的长期个性化：稳定事实、长期偏好、交互协议、决策逻辑、演变趋势。
```

建议保留四层深度扫描：

```text
Layer 1: 基础锚点
  确凿事实、人口统计学特征、当前状态。

Layer 2: 兴趣图谱
  用户投入时间、金钱或注意力的事物，区分活跃爱好、被动消费、休眠兴趣。

Layer 3: 交互协议
  沟通习惯、雷区、工作流偏好。

Layer 4: 认知内核
  决策逻辑、矛盾点、长期驱动力。
```

建议输出模板：

```markdown
# User Narrative Profile

> **Archetype**: 一句话定义用户当前最核心的长期画像。

> **基本信息**
- ...

> **长期偏好**
- ...

## Chapter 1: Context & Current State

## Chapter 2: The Texture of Life

## Chapter 3: Interaction & Cognitive Protocol

### 3.1 How to Speak

### 3.2 How to Think

## Chapter 4: Deep Insights & Evolution

- **矛盾统一性**: ...
- **演变轨迹**: ...
- **涌现特征**:
  - `TagName` - 简短说明
```

## L2ToL3Pipeline 执行流程

建议新增：

```text
src/mcp_memory/pipelines/l2_to_l3.py
src/mcp_memory/services/l3_persona.py
src/mcp_memory/prompts/l3_persona.py
src/mcp_memory/prompts/modules/l3_persona_system.md
```

执行流程：

```text
run_l3(user_id)
  -> 查询 existing L3 persona
  -> strip scene navigation
  -> 如果已有 L3：查询 updated_at > L3.updated_at 的 changed L2 scenes
  -> 如果没有 L3：查询全部 L2 scenes
  -> 判断 PersonaTrigger 等价条件
  -> 如果无需生成：返回 skipped
  -> 查询 all L2 scene index
  -> build L3 prompt
  -> LLM 生成 persona Markdown body
  -> strip markdown fence
  -> escape/sanitize XML-like system tags
  -> append DB scene navigation
  -> upsert memory_items(layer=3, memory_type='persona')
  -> 返回 latest_cursor / memory_id
```

## Repository 设计

建议扩展 `MemoryItemRepository`：

```python
query_l2_for_l3(
    db,
    user_id: str,
    updated_after: datetime | None,
    limit: int,
) -> list[L2SceneRow]

query_all_l2_scenes_for_l3(
    db,
    user_id: str,
    limit: int,
) -> list[L2SceneRow]

get_l3_persona(
    db,
    user_id: str,
) -> L3PersonaRow | None

upsert_l3_persona(
    db,
    obj_in: L3PersonaCreate,
) -> None
```

建议新增 schema：

```python
class L2SceneForL3(BaseModel):
    memory_id: str
    user_id: str
    filename: str
    scene_name: str
    content: str
    summary: str
    heat: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

class L3PersonaCreate(BaseModel):
    memory_id: str
    user_id: str
    content: str
    source_l2_ids: list[str]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

class L2ToL3Result(BaseModel):
    input_count: int
    changed_count: int
    stored: bool
    skipped: bool
    latest_cursor: datetime | None
    memory_id: str | None
```

## Scheduler 接入点

当前 `mcp-memory` 的 `services/pipeline_scheduler.py` 已负责：

```text
L0 notify
  -> L0->L1
  -> L1 成功后设置 L2 timer
  -> L2 timer 到期后执行 L1->L2
```

L3 接入后建议扩展：

```text
run_l2 成功
  -> 如果 result.stored_count > 0:
       notify_l3_after_l2(user_id)
```

L3 调度应是 user 级别：

```python
_l3_tasks: dict[str, asyncio.Task[Any]]
_l3_pending: set[str]
```

本阶段不实现 `persona_state`。如果 L3 正在运行时又有新的 L2 完成，只把 user_id 放入 `_l3_pending`；当前任务结束后再检查 pending 并补跑一轮。

## Config 设计

建议新增配置：

```yaml
memory:
  persona:
    enabled: true
    maxScenes: 15
    triggerEveryN: 50
    maxLength: 2000
```

对应 `Settings`：

```text
MEMORY_PERSONA_ENABLED: bool = True
MEMORY_MAX_SCENES: int = 15
MEMORY_PERSONA_TRIGGER_EVERY_N: int = 50
MEMORY_PERSONA_MAX_LENGTH: int = 2000
```

字段语义：

- `enabled`: 是否启用 L2->L3 persona 生成。
- `maxScenes`: L3 最多读取多少个 L2 场景作为证据和导航索引。
- `triggerEveryN`: 已有 L3 后，累计多少个变化 L2 才触发增量更新。
- `maxLength`: persona 正文长度约束，传入 L3 prompt。

## 与 L2 的关系

L2 完成后不应该无条件每次都重写 persona，应该先做触发判断：

```text
if no L2 scenes:
  skip
elif no existing L3:
  generate full persona
elif changed_l2_count >= triggerEveryN:
  incremental update
else:
  skip
```

当 `triggerEveryN=1` 时，行为等价于“每次 L2 有变化就尝试 L3”，但仍然会被 `changed_l2_count == 0` 拦住。

## 当前实现范围

本阶段已实现：

1. 新增 L3 配置读取：`memory.persona.enabled`、`maxScenes`、`triggerEveryN`、`maxLength`。
2. 新增 `query_l2_for_l3`、`query_all_l2_scenes_for_l3`、`get_l3_persona`、`upsert_l3_persona`。
3. 新增 `L3PersonaService`：
   - 构造 prompt。
   - 调 LLM。
   - strip markdown fence。
   - strip/append DB scene navigation。
   - 生成稳定 L3 memory_id。
4. 新增 `L2ToL3Pipeline`。
5. `PipelineScheduler.run_l2()` 成功写入 L2 后触发 L3。
6. L3 写入 `memory_items(layer=3, memory_type='persona')`。
7. `PipelineScheduler` 内存中按 user_id 控制 L3 running/pending。

暂未实现：

- `persona_state` 用户级状态表。
- 手动请求 persona update 的 gRPC API。
- L3 延迟 timer。
- L3 retry。
- L3 dead letter。
- 多进程分布式锁。
- profile sync。
- 本地 file backup。

## 风险点

### 1. L3 过度频繁生成

如果把 `triggerEveryN` 设为 `1`，每次 L2 变化都会触发 L3，LLM 成本会升高。

缓解：

- 本地开发阶段可以临时设为 `1`，方便验证。
- 稳定后调成 `3`、`5` 或默认的 `50`。
- 后续加入 `l3MinIntervalSeconds`。

### 2. L3 并发覆盖

多个 session 同时完成 L2，可能同时触发 L3。

缓解：

- `PipelineScheduler._l3_tasks` 防止同一 user 并发。
- `PipelineScheduler._l3_pending` 合并运行期间的新触发。
- `upsert_l3_persona` 使用稳定 memory_id。

### 3. Prompt 写入 navigation

LLM 可能自己输出 scene navigation。

缓解：

- prompt 明确禁止输出 navigation。
- 工程侧 `strip_scene_navigation()` 后再追加最新 navigation。

### 4. Persona 幻觉

L3 容易把 L2 中的短期关注误写成稳定人格。

缓解：

- prompt 明确“只基于 L2 场景证据”。
- 区分稳定偏好、近期关注、待确认点。
- 对低热度、单次场景保持克制表达。

### 5. L3 cursor 语义

如果只用 `updated_at` 游标，多个 L2 同一时间更新可能存在边界问题。

第一阶段可接受。后续可以升级为复合 cursor：

```text
(updated_at, memory_id)
```

或在 `persona_state` 中记录 `last_l3_source_l2_ids`。
本阶段不实现 `persona_state`，如遇到边界问题，优先改成复合 cursor 查询或在 L3 metadata 中记录已消费的 L2 ids。

## 推荐开发顺序

1. 先做 repository 和 schema：能查询 L2、读写 L3。
2. 再做 prompt/service：输入 L2 scenes，输出 persona content。
3. 再做 pipeline：串起查询、触发判断、生成、写库。
4. 再接 scheduler：L2 成功后触发 L3，并用内存 task/pending 控制并发。
5. 最后补 README 项目结构和运行说明。
