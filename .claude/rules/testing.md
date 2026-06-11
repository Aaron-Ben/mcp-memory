# 测试规范

## 测试分层

| 类型 | 目标 |
|------|------|
| 单元测试 | 纯函数、schema、ID 生成、分层规则 |
| Repository 测试 | PGSQL 查询、upsert、软删除、索引相关行为 |
| Pipeline 测试 | L0->L1、L1->L2、L2->L3 的幂等和失败恢复 |
| Retrieval 测试 | 用户隔离、过滤、排序、上下文组装 |
| Adapter 测试 | MCP/HTTP/CLI 输入输出契约 |

## 必测行为

- 同一 L0 重复写入不会产生重复记忆。
- 软删除记忆不会被召回。
- 向量检索不会跨 `user_id`。
- L1 派生结果保留来源 L0。
- L2/L3 更新保留 lineage。
- pipeline step 重试不会破坏数据。

## 数据库测试

- 涉及 PGSQL、JSONB、pgvector 的行为应使用真实 PostgreSQL 或明确兼容的测试容器。
- 不要用 SQLite 证明 pgvector、JSONB、HNSW 行为。
- 迁移文件需要单独验证 upgrade。

## LLM 相关测试

- 单元测试不直接调用真实 LLM。
- LLM 输出解析必须用固定样例测试。
- pipeline 集成测试可使用 fake extractor。
