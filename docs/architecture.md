# PandaMind — AI 模型服务架构设计

> 版本：v0.5
> 更新：2026-06-01

---

## 1. 项目定位

统一的 AI 模型服务平台，核心能力：

- 本地部署模型（Ollama、vLLM）与远程 API 模型（OpenAI、Anthropic、通义千问等）统一管理
- 对外提供 OpenAI 兼容 API，可直接接入现有生态工具
- 提示词模板管理（变量插值、版本历史、分类标签）
- Web UI 本地测试界面（对话测试、提示词编辑、模型配置）

**技术栈基线**：后端 Python 3.11+ / FastAPI，前端 React + Vite，数据库 PostgreSQL，部署 Docker Compose。选择 Python 的核心理由：AI/LLM 生态（LangChain、HuggingFace、vLLM、embedding 模型、RAG 工具链）以 Python 为主流，后期扩展（Agent、RAG、本地推理）无需重写。

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                        Web UI                            │
│          (对话测试 / 提示词管理 / 模型配置)              │
└─────────────────────────┬────────────────────────────────┘
                          │ HTTP / SSE
┌─────────────────────────▼────────────────────────────────┐
│                     API Gateway                          │
│           (限流 / 请求日志 / CORS)              │
└────────┬──────────────┬──────────────┬───────────────────┘
         │              │              │
┌────────▼──────┐ ┌─────▼──────┐ ┌────▼────────────────┐
│   Chat API    │ │ Prompt API │ │  Model Config API   │
│ /v1/chat/...  │ │ /v1/prompts│ │  /v1/models         │
└────────┬──────┘ └─────┬──────┘ └────┬────────────────┘
         │              │              │
┌────────▼──────────────▼──────────────▼──────────────────┐
│                      Core Services                       │
│                                                          │
│  ┌──────────────┐   ┌───────────────┐  ┌─────────────┐  │
│  │ Model Router │   │ Prompt Engine │  │ Key Manager │  │
│  └──────┬───────┘   └───────┬───────┘  └──────┬──────┘  │
│         │                   │                  │         │
│  ┌──────▼───────────────────▼──────────────────▼──────┐  │
│  │               Provider Adapter Layer               │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐  │  │
│  │  │ Ollama   │ │ OpenAI   │ │Anthropic │ │Custom│  │  │
│  │  │ Provider │ │ Provider │ │ Provider │ │  ...  │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────┐
│                      PostgreSQL                          │
│     models / prompts / prompt_versions / conversations   │
└──────────────────────────────────────────────────────────┘

共享类型策略：后端 Pydantic 模型 = source of truth，前端通过 OpenAPI schema 自动生成 TypeScript 类型
（详见 ADR-009 / ADR-010）
```

---

## 3. 模块详细说明

### 3.1 Provider Adapter（提供者适配层）

统一接口，屏蔽不同模型的 API 差异。

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator
from pandamind.schemas.chat import Message, ChatChunk, ChatOptions
from pandamind.schemas.model import ModelInfo, ProviderHealth

class BaseProvider(ABC):
    """所有模型 Provider 实现此接口。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        options: ChatOptions,
    ) -> AsyncIterator[ChatChunk]:
        """流式对话（主要接口）。"""
        ...

    @abstractmethod
    def abort(self, stream_id: str) -> None:
        """主动取消进行中的流式请求。"""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """检测 Provider 是否可用。"""
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """列出该 Provider 下可用模型。"""
        ...


# v1 MVP 实现
class OllamaProvider(BaseProvider): ...        # 本地 Ollama HTTP API
class OpenAICompatibleProvider(BaseProvider): ...  # OpenAI 及所有兼容接口（DeepSeek、Groq 等）

# Phase 2+ 扩展（v1 不实现）
class AnthropicProvider(BaseProvider): ...     # Claude API（格式差异大，需独立适配）
class QwenProvider(BaseProvider): ...          # 通义千问 API
class CustomProvider(BaseProvider): ...        # 自定义 OpenAI 兼容 baseUrl（不做任意 HTTP 适配）
```

**Provider 注册机制**：启动时从数据库加载所有启用的模型配置，实例化对应 Provider 并注册到 Model Router。配置变更后重建 ProviderRegistry 快照，无需重启服务。

### 3.2 Model Router（模型路由）

根据请求 `model` 字段分发到对应 Provider，支持：

- **前缀路由**：`ollama/llama3:8b` → OllamaProvider
- **别名路由**：`fast` → 数据库中配置的别名目标
- **故障转移**：主 Provider 不可用时，按配置切换备用 Provider（可选）

```
请求 model="ollama/llama3:8b"
  → 解析 provider=ollama, model=llama3:8b
  → 查找注册的 OllamaProvider 实例
  → 调用 provider.chat(messages, options)
  → 流式返回
```

### 3.3 Prompt Engine（提示词引擎）

- **变量插值**：`{{variable}}` 语法，渲染时传入变量值
- **版本快照**：每次更新保存历史版本到 `prompt_versions` 表，支持回滚
- **模板组合**：system prompt + few-shot examples + user template 分层组合
- **渲染预览**：`POST /v1/prompts/{id}/render` 传入变量值返回渲染结果，不实际调用模型

### 3.4 Key Manager（密钥管理）

API Key 不明文存入数据库：

- 使用 AES-256-GCM 加密，密钥来自环境变量 `ENCRYPTION_KEY`
- 数据库存储密文，读取时解密后注入 Provider
- UI 展示时只显示末 4 位（`sk-...xxxx`）

### 3.5 API Gateway

- **认证**：JWT Bearer Token，本地开发可通过 `AUTH_DISABLED=true` 关闭
- **限流**：基于 IP + API Key 双维度，使用 `slowapi`（基于 Starlette）
- **日志**：结构化日志（structlog），记录请求耗时、token 用量、Provider 来源
- **CORS**：可配置允许来源，默认只允许 localhost

### 3.6 Health Check（健康检查）

```
GET /health              # 服务自身状态
GET /v1/models/{id}/ping  # 检测指定模型 Provider 连通性
```

启动时自动对所有启用的 Provider 做一次 healthCheck，不可用的标记为 `status=unreachable` 并在 UI 中提示。

---

## 4. 技术选型

| 层次 | 技术 | 理由 |
|------|------|------|
| 后端框架 | **Python 3.11+ / FastAPI** | 异步、SSE 原生支持强、Pydantic 验证内建，AI 生态主流 |
| 数据验证 | **Pydantic v2** | 类型验证、自动生成 OpenAPI schema、前后端共享模型 |
| 数据库 | **PostgreSQL** | 原生 JSONB、全文检索、生产级可靠性 |
| ORM | **SQLAlchemy 2.0 async + Alembic** | 成熟稳定、原生 async、PG JSONB 一等支持、迁移工具完善 |
| 密钥加密 | **`cryptography` 库（AES-256-GCM）** | 事实标准，无外部依赖 |
| Web UI | **React + Vite** | 生态成熟，开发体验好 |
| UI 组件库 | **shadcn/ui + Tailwind CSS** | 无样式锁定，可完全定制 |
| 流式通信 | **SSE（Server-Sent Events）** | 单向流，使用 `sse-starlette` 库（Starlette/FastAPI 上层封装，自动处理 ping/id/重连），不要裸用 `StreamingResponse` 手写 SSE 格式 |
| 本地模型运行时 | **Ollama** | 最易用的本地模型管理工具 |
| 包管理 | **pnpm (前端) + uv (后端) monorepo** | 前端 pnpm，后端 Python 用 uv（Rust 实现，比 poetry/pip 快 10-100 倍） |
| 容器化 | **Docker + Docker Compose** | 一键启动 PostgreSQL + 服务 |
| 日志 | **structlog** | 结构化 JSON 日志，pino 等价物 |
| HTTP 客户端 | **httpx** | async 优先、HTTP/2 支持 |
| SSE 服务端 | **sse-starlette** | Starlette/FastAPI 友好的 SSE 封装，避手写协议 |
| 测试 | **pytest + pytest-asyncio + httpx** | Python 测试标准组合 |

> **ADR-009 补充**：前端 package 维持 pnpm monorepo；后端 Python 通过独立的 `pyproject.toml` + `uv` 管理，与前端通过目录结构并列（不混用 pnpm workspace 管 Python 包）。共享类型通过后端 Pydantic 模型自动生成 OpenAPI schema，前端用 `openapi-typescript` 自动生成 TypeScript 类型，避免双写。

---

## 5. 目录结构

```
pandamind/
├── apps/
│   ├── server/                       # Python 后端
│   │   ├── src/
│   │   │   ├── pandamind/
│   │   │   │   ├── providers/        # Provider 适配器
│   │   │   │   │   ├── base.py       # BaseProvider 抽象类
│   │   │   │   │   ├── ollama.py
│   │   │   │   │   ├── openai_compatible.py
│   │   │   │   │   └── registry.py   # ProviderRegistry
│   │   │   │   ├── api/              # FastAPI 路由
│   │   │   │   │   ├── chat.py
│   │   │   │   │   ├── models.py
│   │   │   │   │   ├── prompts.py
│   │   │   │   │   ├── conversations.py
│   │   │   │   │   └── health.py
│   │   │   │   ├── services/
│   │   │   │   │   ├── model_router.py
│   │   │   │   │   ├── prompt_engine.py
│   │   │   │   │   └── key_manager.py
│   │   │   │   ├── db/
│   │   │   │   │   ├── models.py     # SQLAlchemy ORM 模型
│   │   │   │   │   ├── session.py    # async session 工厂
│   │   │   │   │   ├── migrations/   # Alembic 迁移
│   │   │   │   │   └── seed.py       # 初始示例数据
│   │   │   │   ├── schemas/          # Pydantic 模型（请求/响应）
│   │   │   │   │   ├── chat.py
│   │   │   │   │   ├── model.py
│   │   │   │   │   ├── prompt.py
│   │   │   │   │   └── common.py
│   │   │   │   ├── core/             # 核心工具
│   │   │   │   │   ├── config.py     # Settings (pydantic-settings)
│   │   │   │   │   ├── logging.py    # structlog 配置
│   │   │   │   │   ├── middleware.py  # traceId 中间件
│   │   │   │   │   └── exceptions.py # 统一错误响应
│   │   │   │   └── main.py           # FastAPI app 入口
│   │   │   └── tests/                # pytest 测试
│   │   ├── pyproject.toml            # uv 项目配置
│   │   ├── alembic.ini
│   │   └── Dockerfile
│   │
│   └── web/                          # React 前端
│       ├── src/
│       │   ├── components/
│       │   │   ├── chat/             # 对话界面
│       │   │   ├── prompts/          # 提示词管理
│       │   │   ├── models/           # 模型配置
│       │   │   └── ui/               # shadcn 组件
│       │   ├── hooks/
│       │   ├── lib/                  # API 客户端、openapi-typescript 生成
│       │   ├── pages/
│       │   └── main.tsx
│       ├── package.json
│       ├── vite.config.ts
│       └── Dockerfile
│
├── docker-compose.yml
├── docker-compose.dev.yml            # 开发环境（只启动 PostgreSQL）
├── docs/
├── pnpm-workspace.yaml               # 前端 monorepo
└── README.md
```

> **前后端类型共享策略**：后端 Pydantic 模型即 source of truth，启动时通过 `openapi-typescript` 从 `/openapi.json` 自动生成前端 TypeScript 类型到 `apps/web/src/lib/api-types.ts`。**删除**原先的 `packages/shared`，避免双写。前端组件直接 import 生成的类型，编译时类型与后端完全一致。

---

## 6. API 设计

### 6.1 Chat（OpenAI 兼容）

两个 ID 概念需要区分：

- **traceId**：每个 HTTP 请求唯一，用于日志追踪，响应头 `X-Trace-Id` 返回，所有错误响应也携带
- **streamId**：每次流式生成唯一，用于中止生成，SSE 首帧携带，客户端用它调用中止端点

```
POST   /v1/chat/completions    # 发起对话（流式或非流式）
DELETE /v1/chat/{streamId}      # 中止进行中的流式生成
```

请求体：
```
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "ollama/llama3:8b",
  "messages": [
    { "role": "user", "content": "你好" }
  ],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 2048,
  "prompt_template_id": "code-assistant",   // 可选：注入 system prompt
  "template_variables": {                    // 可选：模板变量
    "language": "TypeScript"
  }
}
```

响应头：
- `X-Trace-Id`：traceId，所有请求均有，用于日志追踪
- `X-Stream-Id`：streamId，仅流式请求有，用于中止生成

流式响应遵循 OpenAI SSE 格式（`data: {...}\n\n`），首帧携带 `streamId`。非流式返回标准 JSON。

### 6.2 模型管理

两个概念需要区分：

- **模型配置**（`/v1/models`）：数据库中存储的 Provider 连接配置，用户手动管理
- **可用子模型**（`/v1/models/{id}/list`）：调用 Provider 动态查询该连接下实际可用的模型列表（如 Ollama 已拉取的模型）

```
GET    /v1/models              # 列出数据库中所有模型配置
POST   /v1/models              # 创建模型配置
GET    /v1/models/{id}          # 获取单个模型配置
PUT    /v1/models/{id}          # 更新模型配置（触发 ProviderRegistry 快照重建）
DELETE /v1/models/{id}          # 删除模型配置
GET    /v1/models/{id}/ping     # 检测 Provider 连通性
GET    /v1/models/{id}/list     # 动态查询 Provider 下可用子模型
```

模型配置结构：
```json
{
  "id": "my-llama3",
  "name": "本地 Llama3 8B",
  "provider": "ollama",
  "model": "llama3:8b",
  "baseUrl": "http://localhost:11434",
  "apiKey": null,
  "defaultParams": {
    "temperature": 0.7,
    "maxTokens": 2048
  },
  "aliases": ["fast", "local"],
  "enabled": true
}
```

### 6.3 提示词模板

```
GET    /v1/prompts                    # 列出所有模板（支持 ?tag=&search= 过滤）
POST   /v1/prompts                    # 创建模板
GET    /v1/prompts/{id}                # 获取模板详情
PUT    /v1/prompts/{id}                # 更新模板（自动保存版本快照）
DELETE /v1/prompts/{id}                # 删除模板
POST   /v1/prompts/{id}/render         # 渲染预览（传入变量，返回渲染结果）
GET    /v1/prompts/{id}/versions       # 获取版本历史
POST   /v1/prompts/{id}/rollback/{ver}  # 回滚到指定版本
```

模板结构：
```json
{
  "id": "code-assistant",
  "name": "代码助手",
  "description": "专注代码生成和调试",
  "system": "你是一个专业的 {{language}} 开发者，擅长 {{specialty}}。",
  "userTemplate": "请帮我 {{task}}",
  "variables": [
    { "name": "language", "description": "编程语言", "default": "TypeScript" },
    { "name": "specialty", "description": "专长领域", "default": "后端开发" },
    { "name": "task", "description": "任务描述", "required": true }
  ],
  "tags": ["code", "dev"],
  "version": 3
}
```

### 6.4 对话历史

```
GET    /v1/conversations              # 列出对话历史
GET    /v1/conversations/{id}          # 获取对话详情
DELETE /v1/conversations/{id}          # 删除对话
```

---

## 7. 数据库 Schema（PostgreSQL）

> **ID 生成策略**：所有表的 `id` 字段使用 **nanoid**（21 字符，URL 安全），在应用层生成后写入。不用自增整数（避免枚举攻击），不用 UUID（太长）。SQLAlchemy 层统一封装 `generate_id()` 工具函数（蛇形命名，与 Python 风格一致）。

```sql
-- 模型配置
CREATE TABLE models (
  id            TEXT        PRIMARY KEY,        -- nanoid，应用层生成
  name          TEXT        NOT NULL,
  provider      TEXT        NOT NULL,           -- ollama | openai | anthropic | custom
  model         TEXT        NOT NULL,
  base_url      TEXT,
  api_key_enc   TEXT,                           -- AES-256-GCM 密文
  default_params JSONB      DEFAULT '{}',
  aliases       TEXT[]      DEFAULT '{}',
  enabled       BOOLEAN     DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 提示词模板
CREATE TABLE prompts (
  id            TEXT        PRIMARY KEY,        -- nanoid，应用层生成
  name          TEXT        NOT NULL,
  description   TEXT,
  system        TEXT,
  user_template TEXT,
  variables     JSONB       DEFAULT '[]',
  tags          TEXT[]      DEFAULT '{}',
  version       INTEGER     DEFAULT 1,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 提示词版本历史快照
-- 用硬外键 + CASCADE：版本快照是 prompt 的附属数据，prompt 删除时快照一并清理是正确行为
CREATE TABLE prompt_versions (
  id            SERIAL      PRIMARY KEY,
  prompt_id     TEXT        NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
  version       INTEGER     NOT NULL,
  snapshot      JSONB       NOT NULL,           -- 完整 prompt 快照
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (prompt_id, version)
);

-- 对话历史
-- model_id / prompt_id 用软引用（不加外键约束）
-- 原因：模型或提示词删除后，历史对话仍需可查；model_name 冗余快照保证展示不丢失
CREATE TABLE conversations (
  id            TEXT        PRIMARY KEY,        -- nanoid，应用层生成
  model_id      TEXT        NOT NULL,           -- 软引用 models.id
  model_name    TEXT,                           -- 冗余快照，模型删除后仍可展示
  prompt_id     TEXT,                           -- 软引用 prompts.id
  title         TEXT,                           -- 取首条用户消息前 50 字自动生成
  messages      JSONB       NOT NULL DEFAULT '[]',
  meta          JSONB       DEFAULT '{}',       -- token 用量、耗时、provider 来源等
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- updated_at 自动更新触发器（PostgreSQL 不自动维护）
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_models_updated_at
  BEFORE UPDATE ON models
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_prompts_updated_at
  BEFORE UPDATE ON prompts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_conversations_updated_at
  BEFORE UPDATE ON conversations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 索引
CREATE INDEX idx_prompts_tags ON prompts USING GIN (tags);
CREATE INDEX idx_conversations_model ON conversations (model_id);
CREATE INDEX idx_conversations_created ON conversations (created_at DESC);
```

---

## 8. 错误处理策略

### 统一错误响应格式

所有错误响应使用统一结构，方便前端和外部调用方处理：

```json
{
  "code": "PROVIDER_UNAVAILABLE",
  "message": "Ollama provider is not reachable",
  "details": { "provider": "ollama", "baseUrl": "http://localhost:11434" },
  "traceId": "abc123xyz"
}
```

| 场景 | HTTP 状态 | code |
|------|-----------|------|
| Provider 连接超时 | `503` | `PROVIDER_UNAVAILABLE` |
| API Key 无效 | `401` | `INVALID_API_KEY` |
| 模型配置不存在 | `404` | `MODEL_NOT_FOUND` |
| 流式中断（SSE 内） | — | `STREAM_ERROR`（SSE event） |
| Provider 限流 | `429` | `PROVIDER_RATE_LIMITED` |
| 模板变量缺失 | `400` | `MISSING_TEMPLATE_VARIABLES` |
| 请求参数校验失败 | `400` | `VALIDATION_ERROR` |
| 服务内部错误 | `500` | `INTERNAL_ERROR` |

`traceId` 由服务端生成，通过响应头 `X-Trace-Id` 返回，不信任客户端传入。`details` 字段不暴露 API Key、密码等敏感信息。

---

## 9. 配置管理

环境变量（`.env`）负责**基础设施配置**，数据库负责**业务配置**：

```bash
# .env
DATABASE_URL=postgresql://user:pass@localhost:5432/pandamind
ENCRYPTION_KEY=<base64-encoded-32-byte-key>   # API Key 加密主密钥（base64 编码 32 字节）
AUTH_DISABLED=true              # 本地开发关闭认证
PORT=3000
LOG_LEVEL=info
```

模型的 `baseUrl`、`apiKey`、参数等业务配置全部存数据库，通过 UI 或 API 管理，不写死在环境变量里。

**ENCRYPTION_KEY 编码格式**：`ENCRYPTION_KEY` 是 **base64 编码**的 32 字节随机值（启动时 `base64.b64decode` 后必须等于 32 字节，否则拒绝启动）。生成方式：
```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```
不直接存 32 字符字符串（容易和 32 字节混淆，base64 编码后是 44 字符无歧义）。

---

## 10. 扩展路径

| 阶段 | 内容 |
|------|------|
| **Phase 1** | 核心功能：Ollama + OpenAI，PostgreSQL，Web UI，单机 Docker 部署 |
| **Phase 2** | 多用户：JWT 用户系统，API Key 管理，用量统计 Dashboard |
| **Phase 3** | 高可用：请求队列（Celery/RQ），多 Provider 负载均衡，故障转移 |
| **Phase 4** | 能力扩展：RAG 知识库，Function Calling，Agent 工作流 |

---

## 11. ADR — 架构决策记录

### ADR-001 Provider 抽象层

**决策**：所有模型 Provider 实现 `BaseProvider` 抽象类，Model Router 只依赖抽象。

**原因**：不同 Provider（Ollama、OpenAI、Anthropic）的 HTTP API 格式差异大，直接调用会导致路由层充斥 if/else。抽象后新增 Provider 只需实现基类，不改上层代码。

**代价**：每个 Provider 需要单独维护格式转换逻辑。

---

### ADR-002 OpenAI 兼容 API

**决策**：对外暴露的 Chat API 遵循 OpenAI `/v1/chat/completions` 格式。

**原因**：Continue.dev、Open WebUI、Cursor 等主流工具均支持 OpenAI 格式，兼容后可直接接入，无需额外适配层。

**代价**：OpenAI 格式不能完整表达所有 Provider 的特有能力（如 Anthropic 的 extended thinking），特有参数通过扩展字段传递。

---

### ADR-003 SSE 流式输出

**决策**：流式输出使用 SSE（Server-Sent Events），不用 WebSocket。

**原因**：流式输出是单向的（服务端 → 客户端），SSE 足够且更简单，HTTP/2 下性能无差异，浏览器原生支持无需额外库。使用 `sse-starlette` 而非裸 `StreamingResponse`，避免手写 `data: ...\n\n` 协议、ping 保活、客户端重连等细节。

**代价**：SSE 在某些反代（Nginx）配置下会被缓冲，需要配置 `X-Accel-Buffering: no`。

---

### ADR-004 SQLAlchemy 2.0 async + Alembic

**决策**：使用 SQLAlchemy 2.0 async ORM + Alembic 迁移工具，不用 Drizzle、Prisma、SQLModel。

**原因**：SQLAlchemy 2.0 是 Python 生态最成熟、async 原生支持最完善的 ORM；Alembic 迁移工具与 SQLAlchemy 深度集成；对 PostgreSQL 原生类型（`JSONB`、`TEXT[]`）支持直接。SQLModel 抽象层太薄，对复杂查询反而是负担。

**代价**：API 较 Prisma/Drizzle 更"重"，需要熟悉 `select()` / `Session.execute()` 风格。

---

### ADR-005 JSONB 存储对话消息

**决策**：`conversations.messages` 用 JSONB 存整个消息数组，不拆 `conversation_messages` 表。

**原因**：MVP 阶段对话消息以整体读写为主，JSONB 简单直接，无需 JOIN。

**代价**：长期会影响分页、单条消息更新和 token 统计查询。Phase 2 前需评估是否拆表。

---

### ADR-006 软引用历史记录

**决策**：`conversations` 表的 `model_id` / `prompt_id` 不加外键约束，用软引用 + 冗余快照。

**原因**：模型或提示词删除后，历史对话仍需可查。硬外键会导致删除模型时历史记录无法访问或被级联删除。

**代价**：数据一致性由应用层保证，不依赖数据库约束。

---

### ADR-007 Provider 注册快照重建策略

**决策**：模型配置更新后，重建整个 ProviderRegistry 快照，不做细粒度热替换。

**原因**：细粒度热替换需要处理并发请求期间的 Provider 切换、旧请求收尾、失败回滚等复杂场景。重建快照简单可靠：新请求用新 registry，进行中的请求持有旧 Provider 引用直到完成。

**代价**：极短暂的切换窗口内新旧 Provider 并存，内存占用略高。

---

### ADR-008 nanoid 作为主键

**决策**：所有表的 `id` 字段使用 nanoid（21 字符），在应用层生成。

**原因**：比自增整数安全（避免枚举攻击），比 UUID 短（URL 友好），应用层生成无需数据库往返。

**代价**：需要在应用层统一封装 `generate_id()` 函数（蛇形命名，符合 Python 风格），不能依赖数据库默认值。

---

### ADR-009 后端技术栈：Python + FastAPI

**决策**：后端使用 Python 3.11+ + FastAPI + Pydantic v2。

**原因**：
- AI/LLM 生态（LangChain、HuggingFace、vLLM、embedding 模型、RAG 工具链）以 Python 为主流，Phase 4 接入 RAG/Agent 无需重写
- FastAPI 异步性能优秀，Pydantic v2 自动生成 OpenAPI schema
- 后期本地模型推理、embedding 计算、向量检索需要 Python 工具链，混语言栈（Node 网关 + Python 推理）增加复杂度

**代价**：失去前后端 TypeScript 共享类型的便利。通过 OpenAPI 自动生成弥补：后端 Pydantic 模型即 source of truth，前端用 `openapi-typescript` 从 `/openapi.json` 生成 TypeScript 类型。

---

### ADR-010 Pydantic 模型即 source of truth

**决策**：后端 Pydantic 模型定义所有请求/响应类型，前端通过 `openapi-typescript` 从 OpenAPI schema 自动生成 TypeScript 类型。

**原因**：双写类型（Python Pydantic + TypeScript 共享包）会漂移，是已知反模式。OpenAPI 自动生成是单一来源（SSOT）方案，编译时类型一致，运行时由 FastAPI 校验。

**代价**：前端类型生成需在 `pnpm dev` 前跑 `pnpm gen:api`，增加一次构建步骤。
