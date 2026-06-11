# PGSQL 存储规范

## 核心表设计

PGSQL 后端以 `memory_items` 为核心表承载 L0/L1/L2/L3。除非有明确理由，不为每个层级拆独立表。

建议核心字段：

| 字段 | 用途 |
|------|------|
| `memory_id` | 全局唯一且幂等的记忆 ID |
| `user_id` | 租户/用户/服务隔离键 |
| `layer` | 0 到 3，对应 L0-L3 |
| `memory_type` | 消息角色、事实类型、场景类型或画像类型 |
| `content` | 可检索文本 |
| `embedding` | pgvector 向量 |
| `priority` | 召回优先级，数值越小优先级越高 |
| `scene_name` | L2/L3 场景或主题 |
| `source_conversation_id` | 来源会话 |
| `source_session_key` | 来源 session |
| `metadata` | JSONB 扩展字段 |
| `status` | active, archived 等 |
| `is_deleted` | 软删除标记 |
| `created_at`, `updated_at`, `deleted_at` | 无时区东八区时间 |

## 幂等键

写入必须优先设计稳定 `memory_id`。

建议：

- L0：由 `user_id + source_conversation_id + message_id` 派生。
- L1：由 `user_id + source_l0_ids + extractor_version + normalized_content_hash` 派生。
- L2：由 `user_id + scene_name + source_l1_group_hash` 或版本化策略派生。
- L3：由 `user_id + profile_type + subject_key` 派生。

禁止：

- 对可重试写入使用纯随机 ID。
- 依赖数据库自增 ID 作为业务幂等依据。

## JSONB metadata

`metadata` 只放扩展字段，不替代主查询字段。

必须稳定的 key：

- `source_memory_ids`: 派生来源。
- `confidence`: 置信度。
- `extractor_version`: 抽取器版本。
- `last_seen_at`: 最近证据时间。
- `evidence_count`: 证据数量。

如果字段会高频查询，应提升为普通列，而不是长期藏在 JSONB 中。

## pgvector

- 向量维度必须和 embedding 模型一致。
- 维度变化必须通过迁移显式处理，不允许静默改列。
- HNSW 索引必须带 `embedding IS NOT NULL` 条件。
- 检索时必须同时过滤 `user_id`、`is_deleted`、`status`，避免跨用户召回。

## 软删除

- 默认查询必须过滤 `is_deleted IS FALSE`。
- 软删除时必须设置 `deleted_at`。
- 恢复时必须清空 `deleted_at`。
- 不允许业务代码直接物理删除记忆，除非是明确的数据清理任务。

## 索引

至少应覆盖：

- `(user_id, layer, status)`
- `(user_id, source_conversation_id)`
- `(memory_type, status)`
- `updated_at`
- `embedding` HNSW 条件索引

新增查询前先说明访问模式，再决定是否加索引。
