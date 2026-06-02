# PandaMind 正式外部 API 架构与设计

> 日期：2026-06-02
>
> 目标：把 PandaMind 从“本地 Web 管理 + 对话测试工具”演进为可供第三方系统稳定接入的外部 API 服务。
>
> 范围：认证鉴权、调用方管理、API Key、配额限流、用量计量、审计日志、API 版本、错误协议、文档、实施路线。

---

## 1. 背景与问题

当前 PandaMind 已经具备接口雏形：

- `POST /v1/chat/completions`：OpenAI 风格对话接口
- `POST /v1/process`：文本 + 提示词模板 + 模型的处理接口
- `/v1/models`：模型配置管理
- `/v1/prompts`：提示词模板管理
- `GET /v1/chat/stats`：基础用量统计

但当前能力更偏 MVP 和本地管理，不等同于“正式外部 API 平台”。正式对外需要解决：

- 谁可以调用
- 可以调用哪些接口
- 每个调用方可以用哪些模型和提示词
- 每分钟、每天、每月可以调用多少
- 如何追踪每次调用、排查问题和计费用量
- API 变更如何保持兼容
- 如何保护内部模型配置、API Key 和提示词资产

---

## 2. 设计目标

### 2.1 功能目标

- 支持第三方系统通过 API Key 调用 PandaMind。
- 支持外部调用方调用 Chat API 和 Process API。
- 支持调用方级别的权限、模型范围、提示词范围控制。
- 支持按调用方统计请求数、token、耗时、费用估算。
- 支持基础限流和配额，防止滥用。
- 支持审计日志和 traceId，便于排障。
- 支持 API 版本管理，降低升级破坏性。
- 提供机器可读 OpenAPI 文档和人工使用指南。

### 2.2 非功能目标

| 维度 | 目标 |
|------|------|
| 安全性 | API Key 不明文存储；外部调用方不能访问内部管理接口 |
| 可用性 | Provider 故障时返回明确错误，不静默失败 |
| 可观测性 | 每次调用有 `traceId`、调用方、模型、耗时、token、状态码 |
| 可维护性 | 管理面和调用面分离，避免路由权限混乱 |
| 可扩展性 | 后续可接入 Redis 限流、计费系统、外部 API Gateway |
| 简单性 | MVP 阶段不引入多租户复杂平台，不做过早网关化 |

---

## 3. 核心结论

正式外部 API 需要分为两类平面：

| 平面 | 面向对象 | 认证方式 | 典型接口 |
|------|----------|----------|----------|
| 管理面 Admin API | 管理员 / Web UI | JWT Bearer Token | `/v1/models`、`/v1/prompts`、`/v1/api-clients` |
| 调用面 Public API | 外部系统 / 第三方服务 | API Key | `/v1/chat/completions`、`/v1/process` |

关键设计原则：

- Web UI 登录 token 不作为外部系统长期调用凭证。
- 外部 API Key 不允许访问模型配置、提示词编辑等管理接口。
- 内部 Provider API Key 与外部调用 API Key 是两套不同密钥。
- 外部调用方只看到允许使用的模型别名和公开提示词 ID，不看到内部 Provider 连接信息。

---

## 4. 推荐总体架构

```
┌───────────────────────────────┐
│        External Systems        │
│   CRM / Bot / Workflow / App   │
└───────────────┬───────────────┘
                │ API Key
                ▼
┌──────────────────────────────────────────────┐
│              Public API Layer                │
│  API Key Auth / Scope / Rate Limit / Quota   │
│  TraceId / Request Log / Error Envelope      │
└───────────────┬──────────────────────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
┌──────────────┐  ┌────────────────┐
│   Chat API   │  │   Process API   │
│ /v1/chat/... │  │  /v1/process    │
└──────┬───────┘  └───────┬────────┘
       │                  │
       ▼                  ▼
┌──────────────────────────────────────────────┐
│              Core AI Services                │
│ ProviderRegistry / PromptEngine / KeyManager │
└───────────────┬──────────────────────────────┘
                ▼
┌──────────────────────────────────────────────┐
│                  Providers                   │
│       Ollama / OpenAI Compatible / ...       │
└──────────────────────────────────────────────┘


┌───────────────────────────────┐
│             Web UI             │
└───────────────┬───────────────┘
                │ JWT
                ▼
┌──────────────────────────────────────────────┐
│              Admin API Layer                 │
│  Login / Model Config / Prompt Management    │
│  API Client Management / Usage Reports       │
└──────────────────────────────────────────────┘
```

---

## 5. API 分层设计

### 5.1 Public API

Public API 是正式给外部系统调用的接口。

建议保留：

| 接口 | 用途 |
|------|------|
| `POST /v1/chat/completions` | OpenAI 兼容对话 |
| `POST /v1/process` | 按提示词模板处理文本 |
| `GET /v1/public/models` | 列出调用方可用模型别名 |
| `GET /v1/public/prompts` | 列出调用方可用公开提示词 |
| `GET /v1/public/usage` | 查看当前 API Key 的用量 |

不建议对外开放：

| 接口 | 原因 |
|------|------|
| `GET /v1/models` | 会暴露内部 Provider 配置 |
| `POST /v1/models` | 外部调用方不应创建模型连接 |
| `PUT /v1/models/{id}` | 风险过高，可能影响全局路由 |
| `DELETE /v1/models/{id}` | 破坏性操作 |
| `POST /v1/prompts` | 外部调用方不应默认创建内部模板 |
| `PUT /v1/prompts/{id}` | 会修改共享提示词资产 |
| `DELETE /v1/prompts/{id}` | 破坏性操作 |

### 5.2 Admin API

Admin API 面向管理员和 Web UI。

建议范围：

| 接口组 | 能力 |
|--------|------|
| `/v1/auth/*` | 管理员登录 |
| `/v1/models/*` | 模型 Provider 配置管理 |
| `/v1/prompts/*` | 提示词模板管理 |
| `/v1/api-clients/*` | 外部调用方管理 |
| `/v1/api-keys/*` | API Key 创建、禁用、轮换 |
| `/v1/admin/usage/*` | 全局用量统计 |
| `/v1/admin/audit-logs/*` | 审计日志查询 |

---

## 6. 认证与鉴权设计

### 6.1 管理面 JWT

管理面继续使用 JWT Bearer Token。

用途：

- Web UI 登录
- 管理模型配置
- 管理提示词
- 管理外部调用方
- 查看全局统计

实现建议：

- `require_admin_auth`：校验 JWT。
- `AUTH_DISABLED=true` 只允许本地开发使用。
- 生产环境必须要求 `AUTH_DISABLED=false`。

### 6.2 调用面 API Key

外部 API 使用 API Key，不使用管理员 JWT。

请求格式：

```http
Authorization: Bearer pmk_live_xxx
```

或：

```http
X-API-Key: pmk_live_xxx
```

推荐统一使用 `Authorization: Bearer`，原因是：

- 兼容 OpenAI SDK 的调用习惯。
- 对接工具链更简单。
- 避免同时支持多种认证头造成实现分支。

### 6.3 API Key 格式

建议格式：

```text
pmk_live_<public_id>_<secret>
pmk_test_<public_id>_<secret>
```

字段含义：

| 字段 | 说明 |
|------|------|
| `pmk` | PandaMind Key 前缀 |
| `live/test` | 环境标识 |
| `public_id` | 可公开定位 key 记录的短 ID |
| `secret` | 随机密钥主体，只展示一次 |

存储原则：

- 数据库不存明文 API Key。
- `secret` 只保存哈希，例如 `sha256(secret + salt)` 或 Argon2。
- 展示时只显示前缀和末 4 位。
- 创建时只返回一次明文，后续不可再次查看。

### 6.4 Scope 权限

API Key 至少支持以下 scope：

| Scope | 说明 |
|-------|------|
| `chat:invoke` | 允许调用 `/v1/chat/completions` |
| `process:invoke` | 允许调用 `/v1/process` |
| `models:list` | 允许查看可用公开模型 |
| `prompts:list` | 允许查看可用公开提示词 |
| `usage:read` | 允许查看自己的用量 |

MVP 可以只做 `chat:invoke` 和 `process:invoke`，其他 scope 预留到后续。

### 6.5 资源权限

除了 scope，还需要限制可用资源：

| 权限 | 说明 |
|------|------|
| `allowed_model_ids` | API Key 可调用的模型 ID 或别名 |
| `allowed_prompt_ids` | API Key 可使用的提示词 ID |
| `allowed_origins` | 可选，浏览器来源白名单 |
| `allowed_ips` | 可选，服务端调用方 IP 白名单 |

默认策略：

- 未配置 `allowed_model_ids` 时不允许调用任何模型。
- 未配置 `allowed_prompt_ids` 时不允许调用任何提示词模板。
- 管理员明确授权后才能使用。

这样更符合最小权限原则。

---

## 7. 数据模型设计

### 7.1 api_clients

外部调用方主体。

```sql
CREATE TABLE api_clients (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  description     TEXT,
  owner_email     TEXT,
  status          TEXT NOT NULL DEFAULT 'active',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

状态：

| status | 说明 |
|--------|------|
| `active` | 正常 |
| `disabled` | 禁用 |
| `suspended` | 因异常或欠费暂停 |

### 7.2 api_keys

外部调用凭证。

```sql
CREATE TABLE api_keys (
  id                  TEXT PRIMARY KEY,
  client_id           TEXT NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
  public_id           TEXT NOT NULL UNIQUE,
  name                TEXT NOT NULL,
  key_prefix          TEXT NOT NULL,
  key_hash            TEXT NOT NULL,
  key_last4           TEXT NOT NULL,
  environment         TEXT NOT NULL DEFAULT 'live',
  scopes              JSONB NOT NULL DEFAULT '[]',
  allowed_model_ids   JSONB NOT NULL DEFAULT '[]',
  allowed_prompt_ids  JSONB NOT NULL DEFAULT '[]',
  allowed_ips         JSONB NOT NULL DEFAULT '[]',
  allowed_origins     JSONB NOT NULL DEFAULT '[]',
  status              TEXT NOT NULL DEFAULT 'active',
  expires_at          TIMESTAMPTZ,
  last_used_at        TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

索引建议：

```sql
CREATE UNIQUE INDEX idx_api_keys_public_id ON api_keys(public_id);
CREATE INDEX idx_api_keys_client_id ON api_keys(client_id);
CREATE INDEX idx_api_keys_status ON api_keys(status);
```

### 7.3 api_usage_events

每次外部调用记录。

```sql
CREATE TABLE api_usage_events (
  id                    TEXT PRIMARY KEY,
  trace_id              TEXT NOT NULL,
  client_id             TEXT NOT NULL,
  api_key_id            TEXT NOT NULL,
  endpoint              TEXT NOT NULL,
  method                TEXT NOT NULL,
  model_id              TEXT,
  prompt_id             TEXT,
  status_code           INTEGER NOT NULL,
  error_code            TEXT,
  prompt_tokens         INTEGER NOT NULL DEFAULT 0,
  completion_tokens     INTEGER NOT NULL DEFAULT 0,
  total_tokens          INTEGER NOT NULL DEFAULT 0,
  provider_latency_ms   INTEGER,
  total_latency_ms      INTEGER,
  request_bytes         INTEGER,
  response_bytes        INTEGER,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

索引建议：

```sql
CREATE INDEX idx_usage_client_created ON api_usage_events(client_id, created_at DESC);
CREATE INDEX idx_usage_key_created ON api_usage_events(api_key_id, created_at DESC);
CREATE INDEX idx_usage_model_created ON api_usage_events(model_id, created_at DESC);
CREATE INDEX idx_usage_trace_id ON api_usage_events(trace_id);
```

### 7.4 api_rate_limits

调用方限流和配额配置。

```sql
CREATE TABLE api_rate_limits (
  id                    TEXT PRIMARY KEY,
  client_id             TEXT NOT NULL REFERENCES api_clients(id) ON DELETE CASCADE,
  api_key_id            TEXT REFERENCES api_keys(id) ON DELETE CASCADE,
  rpm                   INTEGER,
  rpd                   INTEGER,
  monthly_tokens        BIGINT,
  monthly_requests      BIGINT,
  max_concurrent        INTEGER,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

MVP 可以先把限流配置放在 `api_keys` JSONB 字段里。独立表适合后续复杂化。

### 7.5 audit_logs

管理面审计日志。

```sql
CREATE TABLE audit_logs (
  id              TEXT PRIMARY KEY,
  trace_id        TEXT NOT NULL,
  actor_type      TEXT NOT NULL,
  actor_id        TEXT,
  action          TEXT NOT NULL,
  resource_type   TEXT NOT NULL,
  resource_id     TEXT,
  before          JSONB,
  after           JSONB,
  ip              TEXT,
  user_agent      TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

审计事件示例：

- 创建 API Client
- 创建 API Key
- 禁用 API Key
- 轮换 API Key
- 修改 allowed models
- 修改 allowed prompts
- 修改限流配额

---

## 8. 请求处理流程

### 8.1 Chat API 流程

```
1. 接收 POST /v1/chat/completions
2. TraceIdMiddleware 生成 traceId
3. PublicAuthDependency 解析 API Key
4. 校验 key 状态、过期时间、scope
5. 校验调用方是否允许使用请求中的 model
6. 限流检查：RPM、并发数、月度 token/request 配额
7. 调用 ProviderRegistry resolve(model)
8. 执行 provider.chat
9. 流式或非流式返回
10. 聚合 usage、latency、status
11. 写入 api_usage_events 和 conversations
```

### 8.2 Process API 流程

```
1. 接收 POST /v1/process
2. TraceIdMiddleware 生成 traceId
3. PublicAuthDependency 解析 API Key
4. 校验 process:invoke scope
5. 校验 allowed_model_ids
6. 校验 allowed_prompt_ids
7. 加载 prompt 模板
8. 校验变量并渲染 system/user prompt
9. 调用 Provider
10. 返回 JSON 结果
11. 写入 api_usage_events
```

### 8.3 鉴权失败返回

```json
{
  "code": "UNAUTHORIZED",
  "message": "Invalid API key",
  "details": null,
  "traceId": "abc123"
}
```

### 8.4 权限不足返回

```json
{
  "code": "FORBIDDEN",
  "message": "API key is not allowed to use this model",
  "details": {
    "model": "gpt-4o"
  },
  "traceId": "abc123"
}
```

### 8.5 限流返回

```json
{
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded",
  "details": {
    "limit": 60,
    "window": "1m"
  },
  "traceId": "abc123"
}
```

响应头：

```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1717339200
Retry-After: 30
```

---

## 9. API 协议设计

### 9.1 统一响应头

所有接口返回：

| Header | 说明 |
|--------|------|
| `X-Trace-Id` | 服务端生成的请求追踪 ID |
| `X-RateLimit-Limit` | 当前窗口请求上限 |
| `X-RateLimit-Remaining` | 当前窗口剩余额度 |
| `X-RateLimit-Reset` | 当前窗口重置时间 |

流式接口额外返回：

| Header | 说明 |
|--------|------|
| `X-Stream-Id` | 用于取消流式请求 |

### 9.2 错误码

建议新增外部 API 稳定错误码：

| code | HTTP | 说明 |
|------|------|------|
| `UNAUTHORIZED` | 401 | 缺少或无效 API Key |
| `FORBIDDEN` | 403 | API Key 无权访问资源 |
| `API_KEY_DISABLED` | 403 | API Key 被禁用 |
| `API_KEY_EXPIRED` | 403 | API Key 已过期 |
| `RATE_LIMIT_EXCEEDED` | 429 | 超过限流 |
| `QUOTA_EXCEEDED` | 429 | 超过配额 |
| `MODEL_NOT_ALLOWED` | 403 | 无权使用该模型 |
| `MODEL_NOT_FOUND` | 404 | 模型不存在或未注册 |
| `PROMPT_NOT_ALLOWED` | 403 | 无权使用该提示词 |
| `PROMPT_NOT_FOUND` | 404 | 提示词不存在 |
| `MISSING_TEMPLATE_VARIABLES` | 400 | 缺少模板变量 |
| `PROVIDER_UNAVAILABLE` | 502 | Provider 不可用 |
| `PROVIDER_TIMEOUT` | 504 | Provider 超时 |
| `VALIDATION_ERROR` | 422 | 请求格式错误 |

### 9.3 API 版本策略

短期：

- 继续使用 `/v1/...`。
- 所有破坏性变更必须新建 `/v2/...`。
- 同一版本内只允许增加字段，不删除字段、不改变字段含义。

中期：

- OpenAPI schema 输出稳定版本。
- 人工文档标注“最后更新日期”和“兼容版本”。
- 增加 `Deprecation` 和 `Sunset` 响应头提示弃用接口。

---

## 10. 限流与配额设计

### 10.1 MVP 限流

MVP 可以先做应用内限流：

- 按 API Key 维度限制 RPM。
- 按 API Key 维度限制并发流式请求数。
- 按 API Key 维度统计每日请求数。

适用场景：

- 单实例部署
- 本地或小规模内部使用
- 快速保护系统避免明显滥用

不足：

- 多实例部署时限流不准确。
- 进程重启会丢失内存计数。

### 10.2 生产限流

生产建议引入 Redis：

- `rate:{api_key_id}:{minute}`：分钟请求计数
- `quota:{api_key_id}:{month}`：月度请求/token 计数
- `concurrency:{api_key_id}`：并发请求计数

限流维度：

| 维度 | 说明 |
|------|------|
| API Key | 防止单 key 滥用 |
| Client | 防止同一调用方创建多个 key 绕过限制 |
| IP | 防止异常来源攻击 |
| Endpoint | 区分 chat/process/list |
| Model | 对高成本模型设置更严格限制 |

---

## 11. 用量计量与审计

### 11.1 用量计量

每次外部调用至少记录：

- `trace_id`
- `client_id`
- `api_key_id`
- `endpoint`
- `model_id`
- `prompt_id`
- `status_code`
- `error_code`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `provider_latency_ms`
- `total_latency_ms`
- `created_at`

用途：

- 调用方账单或成本分摊
- 模型性能分析
- 调用方行为分析
- SLA 排障

### 11.2 审计日志

审计日志关注“谁改了配置”，不是每次调用。

必须审计：

- API Key 创建、禁用、轮换
- API Client 创建、禁用
- 修改权限范围
- 修改配额
- 模型配置变更
- 提示词模板变更

审计日志不应记录：

- 明文 API Key
- 明文 Provider API Key
- 用户输入全文，除非明确有合规要求和脱敏策略

---

## 12. 安全设计

### 12.1 密钥安全

规则：

- 外部 API Key 明文只在创建时返回一次。
- 数据库只保存 key hash、前缀、末 4 位。
- Provider API Key 继续使用 AES-256-GCM 加密。
- 日志中脱敏 `Authorization`、`api_key`、`token`、`password`。
- API Key 轮换时允许旧 key 和新 key 短暂并行。

### 12.2 输入安全

所有 Public API 应使用 Pydantic schema：

- 限制 `messages` 长度
- 限制单条 message 长度
- 限制 `text` 长度
- 限制 `variables` key/value 数量和长度
- 限制 `model`、`prompt_id` 格式
- 限制 `temperature`、`top_p`、`max_tokens` 范围

### 12.3 输出安全

外部响应不得包含：

- Provider API Key
- 内部模型 baseUrl
- 数据库内部配置
- 其他调用方 ID
- 管理员身份信息

### 12.4 管理面保护

生产环境要求：

- `AUTH_DISABLED=false`
- 强 JWT secret
- CORS 只允许明确域名
- 管理接口不暴露给公网，或至少加 IP allowlist / VPN / 反代保护
- 禁止默认密码进入生产

### 12.5 OWASP 风险映射

| 风险 | 防护 |
|------|------|
| Broken Access Control | 管理面和调用面分离，scope + resource 权限 |
| Cryptographic Failures | API Key hash 存储，Provider Key AES-GCM |
| Injection | ORM 参数化查询，Pydantic 入参校验 |
| Security Misconfiguration | 生产禁用 `AUTH_DISABLED=true`，严格 CORS |
| Sensitive Data Exposure | 日志脱敏，响应不暴露内部配置 |

---

## 13. 管理 UI 设计

新增 Web UI 页面建议：

| 页面 | 能力 |
|------|------|
| API Clients | 创建、禁用、查看调用方 |
| API Keys | 创建、禁用、轮换 key，复制一次性明文 |
| Access Control | 配置允许模型、允许提示词、scope |
| Rate Limits | 配置 RPM、每日请求、月度 token、并发数 |
| Usage | 按调用方/API Key/模型/日期查看用量 |
| Audit Logs | 查看管理操作记录 |

MVP 页面优先级：

1. API Clients + API Keys
2. Access Control
3. Usage
4. Audit Logs
5. Rate Limits

---

## 14. OpenAPI 与文档设计

### 14.1 文档分层

建议拆成三类：

| 文档 | 用途 |
|------|------|
| OpenAPI schema | 机器可读，SDK 和类型生成 |
| API 使用指南 | 人工阅读，curl/Python/JS 示例 |
| 管理员指南 | 如何创建 key、授权模型、查看用量 |

### 14.2 OpenAPI 分组

FastAPI tags 建议：

- `public-chat`
- `public-process`
- `public-models`
- `public-usage`
- `admin-auth`
- `admin-models`
- `admin-prompts`
- `admin-api-clients`
- `admin-audit`

### 14.3 SDK 兼容

Chat API 尽量保持 OpenAI 兼容：

- `POST /v1/chat/completions`
- `Authorization: Bearer <api_key>`
- `model`
- `messages`
- `stream`

这样外部系统可用 OpenAI SDK 改 baseURL 接入。

Process API 是 PandaMind 自有能力，应单独提供示例：

```bash
curl -X POST http://localhost:8000/v1/process \
  -H "Authorization: Bearer $PANDAMIND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local-fast",
    "prompt_id": "summary-default",
    "text": "需要处理的文本",
    "variables": {
      "language": "zh-CN"
    }
  }'
```

---

## 15. 实施路线

### Phase 1：最小正式外部 API

目标：可以安全给第三方系统发 API Key 调用。

任务：

- 新增 `api_clients`、`api_keys`、`api_usage_events` 表。
- 实现 API Key 创建、哈希存储、禁用。
- 实现 `require_api_key` 依赖。
- 将 `/v1/chat/completions`、`/v1/process` 接入 API Key 鉴权。
- 保留 Admin JWT 管理面。
- 实现 scope：`chat:invoke`、`process:invoke`。
- 实现 allowed models、allowed prompts 校验。
- 记录基础用量事件。
- 更新 API 使用文档。

验收标准：

- 外部系统使用 API Key 可调用 chat/process。
- 无 API Key 或无效 API Key 返回 401。
- API Key 无权访问某模型时返回 403。
- 每次调用写入 usage event。

### Phase 2：限流与配额

目标：防止滥用并可控成本。

任务：

- 实现 API Key RPM 限流。
- 实现并发流式请求限制。
- 实现每日/月度请求配额。
- 响应头返回 `X-RateLimit-*`。
- 增加 429 错误码。
- 单实例可先内存实现，多实例切换 Redis。

验收标准：

- 超过限制返回 429。
- 流式请求并发超过限制会被拒绝。
- 用量统计可展示剩余额度。

### Phase 3：管理 UI

目标：管理员能通过 Web UI 管理调用方。

任务：

- API Clients 页面。
- API Keys 页面。
- 权限范围配置。
- 用量报表。
- 审计日志页面。

验收标准：

- 管理员无需数据库操作即可创建外部调用方。
- 能为调用方授权模型和提示词。
- 能禁用泄露的 API Key。

### Phase 4：生产增强

目标：支撑多实例和更高可靠性。

任务：

- Redis 限流和配额。
- API Key 轮换流程。
- 更细粒度 usage aggregation。
- Provider timeout/retry 策略。
- 外部网关可选接入：Kong / APISIX / Nginx。
- 监控指标：请求数、错误率、延迟、token、Provider 状态。

验收标准：

- 多实例部署限流准确。
- API Key 轮换不会中断业务。
- 可从监控看出模型和调用方的异常。

---

## 16. 方案对比

### 方案 A：内建 API 管理能力

说明：

- 在 FastAPI 内实现 API Key、权限、限流、用量。

优点：

- 实现快。
- 与现有业务模型结合紧密。
- 运维复杂度低。
- 适合当前 MVP。

缺点：

- 多实例限流需要 Redis。
- 高级网关能力需要逐步补。

推荐程度：优先推荐。

### 方案 B：直接引入外部 API Gateway

说明：

- 使用 Kong、APISIX、Tyk 等网关管理 API Key、限流、路由。

优点：

- 网关能力成熟。
- 多服务和多实例场景更强。
- 标准化运维。

缺点：

- 运维复杂度显著增加。
- 与模型、提示词权限结合仍要在应用层做。
- 对当前阶段偏重。

推荐程度：Phase 4 后评估。

### 方案 C：仅复用现有 JWT

说明：

- 外部系统用 `/v1/auth/login` 获取 JWT，再调用接口。

优点：

- 改动少。

缺点：

- 不适合长期机器调用。
- 难做 per-client 权限、配额、轮换和审计。
- 管理员 token 和外部调用 token 混用，风险高。

推荐程度：不推荐。

---

## 17. 关键 ADR

### ADR-001：管理面和调用面分离

决策：

- 管理面使用 JWT。
- 调用面使用 API Key。

理由：

- 管理员登录和机器调用生命周期不同。
- API Key 更适合轮换、禁用、配额和调用方归属。
- 避免外部系统拿到管理员权限。

取舍：

- 增加一套认证依赖和数据表。
- 换来更清晰的安全边界。

### ADR-002：外部 API Key 只存哈希

决策：

- 外部 API Key 明文只展示一次，数据库只存 hash。

理由：

- 即使数据库泄露，也不能直接拿 key 调用。
- 符合行业 API Key 管理惯例。

取舍：

- 无法找回原 key，只能重新生成。
- 这是安全上可接受且推荐的取舍。

### ADR-003：Public API 不暴露内部模型配置

决策：

- 外部调用方不能访问 `/v1/models` 管理接口。
- 可选提供 `/v1/public/models` 返回授权模型别名。

理由：

- 内部 Provider baseUrl、provider 类型、配置状态属于管理信息。
- 外部调用方只需要知道可调用的公开模型名称。

取舍：

- 需要维护公开模型名和内部模型 ID 的映射。
- 换来更好的安全性和抽象边界。

### ADR-004：先内建，后网关

决策：

- Phase 1-3 在应用内实现 API Key、权限、用量、基础限流。
- Phase 4 再评估外部网关。

理由：

- 当前系统规模和团队阶段更适合 KISS。
- 权限需要绑定模型和提示词，应用内必须实现。

取舍：

- 短期没有完整网关能力。
- 但能更快完成正式对外 API 的最小可用闭环。

---

## 18. 原则评估

### KISS

推荐先做内建 API Key、scope、资源权限、usage event，不直接引入复杂 API Gateway。这样实现路径短，和现有 FastAPI/DB 结构贴合。

### YAGNI

暂不做多租户计费平台、开发者门户、复杂套餐、OAuth2 Client Credentials。当前只需要支持第三方系统稳定、安全调用。

### SOLID

认证鉴权应抽成独立依赖：

- `require_admin_auth`
- `require_api_key`
- `require_scope`
- `require_model_access`
- `require_prompt_access`

业务 handler 不应手写重复权限判断，避免违反单一职责。

### DRY

统一错误结构、traceId、usage event、权限校验和日志脱敏都应集中实现。API 文档以 OpenAPI 为源头，人工文档只写使用场景和示例。

---

## 19. 推荐下一步

优先做 Phase 1，具体顺序：

1. 新增 API Client / API Key / Usage Event 数据表和迁移。
2. 实现 API Key 生成、哈希存储、校验依赖。
3. 给 `/v1/chat/completions` 和 `/v1/process` 接入 API Key 鉴权。
4. 增加 scope、allowed models、allowed prompts 校验。
5. 每次调用写入 `api_usage_events`。
6. 新增最小管理接口：创建 Client、创建 Key、禁用 Key、查看 usage。
7. 更新 API 文档，提供 curl/Python/OpenAI SDK 示例。

完成这些后，PandaMind 才真正具备“正式外部 API 能力”的最小闭环。
