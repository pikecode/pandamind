# 外部 API 能力实现汇总

> 日期：2026-06-02
>
> 范围：汇总本轮外部 API Phase 1 实现与自动化测试结果。本文只记录当前代码已经落地的能力，不把规划中的 API Gateway、限流、配额、审计等能力计入已实现范围。

---

## 1. 实现结论

当前系统已经从“只有 Web/UI 内部对话能力”扩展为“具备最小正式外部 API 调用能力”。

已落地能力包括：

- 外部调用方 Client 管理。
- API Key 生成、哈希存储、鉴权、禁用。
- 基于 scope 的接口权限控制。
- 基于模型 ID、提示词 ID 的资源级授权。
- 外部调用方可用的 Public API。
- Chat 与 Process 调用的外部 API Key 接入。
- 外部调用用量事件落库。
- 自动化单元测试与集成测试。

当前还不是完整 API Gateway。限流、配额、IP 白名单、Origin 白名单、Key 轮换、用量聚合报表、SDK、审计日志等仍属于后续阶段。

---

## 2. 数据库实现

新增迁移：

- `apps/server/alembic/versions/0003_external_api_keys.py`

新增三张核心表：

| 表 | 用途 |
|----|------|
| `api_clients` | 外部调用方主体，例如某个业务系统、客户、集成方 |
| `api_keys` | Client 下的 API Key，存储 hash、public_id、scope、资源授权和状态 |
| `api_usage_events` | 每次外部调用的用量、模型、提示词、trace、延迟等事件 |

ORM 模型位于：

- `apps/server/src/pandamind/db/models.py`

已实现字段覆盖 Phase 1 需要：

- Client 名称、描述、owner、状态。
- Key 的 `public_id`、`key_hash`、`key_prefix`、`key_last4`。
- Key 的 `scopes`、`allowed_model_ids`、`allowed_prompt_ids`。
- Key 状态、过期时间、最近使用时间。
- Usage event 的 `trace_id`、`client_id`、`api_key_id`、endpoint、method、model、prompt、token usage、latency、status。

---

## 3. API Key 服务实现

核心文件：

- `apps/server/src/pandamind/services/api_keys.py`

已实现能力：

- `generate_api_key()`：生成 `pmk_<env>_<public_id>_<secret>` 格式的明文 Key。
- `hash_api_key()`：使用 SHA-256 存储 Key hash，不保存明文。
- `verify_plaintext()`：使用常量时间比较校验明文 Key。
- `authenticate_api_key()`：根据明文 Key 查找、校验并返回 `ApiIdentity`。
- `require_scope()`：校验 scope。
- `has_model_access()`：校验模型授权。
- `has_prompt_access()`：校验提示词授权。

本轮自动化测试发现并修复了一个关键问题：

原实现用 `_` 分隔解析 API Key，但 `public_id` 与 secret 都可能包含 `_`，导致合法 Key 偶发解析失败并返回 401。修复后按固定 21 位 `public_id` 解析，兼容包含 `_` 的 Key。

---

## 4. 认证与鉴权实现

核心文件：

- `apps/server/src/pandamind/core/auth.py`

新增能力：

- `require_public_identity()`：Public API 统一认证入口，优先识别外部 API Key，失败后兼容管理员 JWT。
- `require_external_api_key()`：强制要求外部 API Key，用于 `/v1/public/*` 这类外部专用接口。

设计取舍：

- Chat 与 Process 接口仍兼容管理员 JWT，保证 Web UI 与本地调试不被破坏。
- `/v1/public/*` 明确要求外部 API Key，避免管理员 JWT 混入外部调用方视角。
- 默认 `AUTH_DISABLED=false`，生产环境需要真实鉴权。
- 当本地显式设置 `AUTH_DISABLED=true` 时，认证会被绕过；集成测试中已显式强制真实鉴权路径，避免测试被本地配置误导。

---

## 5. Admin API 实现

核心文件：

- `apps/server/src/pandamind/api/api_clients.py`

已实现接口：

| 方法 | 路径 | 能力 |
|------|------|------|
| `GET` | `/v1/api-clients` | 列出外部 Client |
| `POST` | `/v1/api-clients` | 创建外部 Client |
| `GET` | `/v1/api-clients/{client_id}/keys` | 列出 Client 下的 Key 元数据 |
| `POST` | `/v1/api-clients/{client_id}/keys` | 创建 API Key |
| `POST` | `/v1/api-clients/{client_id}/keys/{key_id}/disable` | 禁用 API Key |
| `GET` | `/v1/api-clients/{client_id}/usage` | 查看某个 Client 的用量事件 |

安全约束：

- 创建 Key 时只返回一次明文 `api_key`。
- 后续列表接口只返回 `key_prefix` 与 `key_last4`，不返回明文。
- 禁用后的 Key 无法继续调用外部接口。

---

## 6. Public API 实现

核心文件：

- `apps/server/src/pandamind/api/public.py`

已实现接口：

| 方法 | 路径 | 能力 |
|------|------|------|
| `GET` | `/v1/public/models` | 返回当前 API Key 授权可见的模型 |
| `GET` | `/v1/public/prompts` | 返回当前 API Key 授权可见的提示词 |
| `GET` | `/v1/public/usage` | 返回当前 API Key 自己的用量事件 |

权限规则：

- `/v1/public/models` 需要 `models:list` scope。
- `/v1/public/prompts` 需要 `prompts:list` scope。
- `/v1/public/usage` 需要 `usage:read` scope。
- 只返回当前 Key 被授权的资源，避免暴露内部全量模型和提示词配置。

---

## 7. Chat 与 Process 外部调用

涉及文件：

- `apps/server/src/pandamind/api/chat.py`
- `apps/server/src/pandamind/api/process.py`
- `apps/server/src/pandamind/services/usage.py`

### 7.1 Chat

接口：

- `POST /v1/chat/completions`

外部 API Key 调用时：

- 需要 `chat:invoke` scope。
- 请求模型必须在 `allowed_model_ids` 中。
- 调用成功后写入 `api_usage_events`。
- 仍保持 OpenAI 兼容响应结构。

### 7.2 Process

接口：

- `POST /v1/process`

外部 API Key 调用时：

- 需要 `process:invoke` scope。
- 请求提示词必须在 `allowed_prompt_ids` 中。
- 请求模型必须在 `allowed_model_ids` 中。
- 调用成功后写入 `api_usage_events`。

---

## 8. 自动化测试实现

新增与扩展测试：

- `apps/server/tests/test_api_keys.py`
- `apps/server/tests/test_external_api_integration.py`

测试覆盖：

| 测试类型 | 覆盖点 |
|----------|--------|
| 单元测试 | Key 生成、hash、解析、常量时间校验、scope、模型授权、提示词授权 |
| 回归测试 | `public_id` 或 secret 含 `_` 时仍能正确解析 API Key |
| 集成测试 | 管理员创建 Client 和 Key |
| 集成测试 | Key 明文只在创建时返回一次 |
| 集成测试 | 缺失认证返回 401 |
| 集成测试 | 模型未授权返回 403 |
| 集成测试 | Chat 成功调用并记录 usage |
| 集成测试 | Process 成功调用并记录 prompt usage |
| 集成测试 | 禁用 Key 后调用被拒绝 |

pytest 配置更新：

- `apps/server/pyproject.toml`

关键配置：

- 注册 `integration` marker。
- 设置 async fixture/test loop scope 为 `session`，避免 asyncpg 连接池跨事件循环复用导致测试不稳定。

---

## 9. 验证结果

最近一次验证命令：

```bash
cd apps/server && uv run python -m pytest
```

结果：

```text
35 passed
```

Lint 验证：

```bash
cd apps/server && uv run python -m ruff check src tests
```

结果：

```text
All checks passed!
```

集成测试依赖：

- 本地 PostgreSQL 可用。
- 数据库迁移已执行到最新版本。

推荐测试前置命令：

```bash
cd apps/server && uv run alembic upgrade head
cd apps/server && uv run python -m pytest
```

---

## 10. 尚未实现能力

以下能力在架构文档中有规划，但本轮没有实现：

| 能力 | 状态 | 建议阶段 |
|------|------|----------|
| API Key 轮换 | 未实现 | Phase 2 |
| API Key 删除或撤销审计 | 未实现 | Phase 2 |
| IP 白名单校验 | 字段已预留，未执行校验 | Phase 2 |
| Origin 白名单校验 | 字段已预留，未执行校验 | Phase 2 |
| 限流 | 未实现 | Phase 2 |
| 月度配额 | 未实现 | Phase 2 |
| 用量聚合报表 | 未实现，仅有事件明细 | Phase 2 |
| 审计日志 | 未实现 | Phase 2 |
| SDK | 未实现 | Phase 3 |
| OpenAPI Schema 精细化 | 部分依赖 FastAPI 自动生成 | Phase 2 |
| 外部调用方自助控制台 | 未实现 | Phase 3 |

---

## 11. 工程原则评估

### KISS

本轮没有引入独立 API Gateway、复杂策略 DSL 或额外服务，直接在现有 FastAPI、SQLAlchemy、PostgreSQL 结构中实现最小可用外部 API 能力。实现路径短，便于调试和测试。

### YAGNI

限流、配额、审计、Key 轮换等能力只保留必要字段或文档规划，没有提前实现复杂机制。当前代码聚焦“能安全创建 Key、鉴权调用、授权资源、记录用量”。

### SOLID

API Key 生成与鉴权集中在 `services/api_keys.py`，用量落库集中在 `services/usage.py`，认证入口集中在 `core/auth.py`，路由层主要负责请求处理与权限调用，职责边界清晰。

### DRY

Chat 与 Process 复用同一套 `ApiIdentity`、scope 校验、资源授权和 usage 记录模型。测试中也通过夹具复用 Client/Key 创建和数据清理逻辑。

---

## 12. 后续建议

建议下一步按以下顺序推进：

1. 补齐外部 API 使用文档中的 API Key 创建、调用、禁用示例。
2. 给 `/v1/public/models` 和 `/v1/public/prompts` 增加集成测试。
3. 增加失败调用 usage 或审计记录策略，明确 401/403 是否进入事件表。
4. 实现最小限流与配额，优先按 `api_key_id` 维度。
5. 将 Admin API 与 Public API 的 OpenAPI response model 从 `dict[str, Any]` 收敛为 Pydantic Schema。
