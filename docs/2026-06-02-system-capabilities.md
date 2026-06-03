# PandaMind 系统功能汇总

> 日期：2026-06-02
>
> 范围：基于当前仓库代码与 `docs/architecture.md`、`docs/development-plan.md`、`docs/2026-06-02-api-usage.md` 汇总。本文区分“已实现”“部分实现”“规划中/暂不具备”，避免把设计规划误认为当前可用能力。

---

## 1. 系统定位

PandaMind 是一个本地优先的 AI 模型服务平台，当前核心目标是：

- 统一管理本地模型与 OpenAI 兼容模型服务
- 对外提供 OpenAI 风格的 Chat API
- 提供提示词模板管理与变量渲染能力
- 提供 Web UI 做模型配置、提示词管理和对话测试
- 通过 PostgreSQL 持久化模型配置、提示词、提示词版本和对话记录

当前技术栈：

| 层次 | 技术 |
|------|------|
| 后端 | Python 3.11+、FastAPI、SQLAlchemy async、Alembic、httpx、structlog |
| 前端 | React、Vite、TypeScript、Tailwind CSS |
| 数据库 | PostgreSQL |
| 部署 | Docker Compose |
| 包管理 | 后端 `uv`，前端 `pnpm` |

---

## 2. 当前已实现能力

### 2.1 后端基础能力

已具备：

- FastAPI 应用入口：`apps/server/src/pandamind/main.py`
- 健康检查：`GET /health`
- CORS 中间件，允许来源由 `ALLOWED_ORIGINS` 配置
- 服务端生成 `traceId`，通过 `X-Trace-Id` 响应头返回
- 全局异常处理，错误结构为 `{ code, message, details, traceId }`
- 结构化日志，使用 `structlog`
- 日志敏感字段脱敏：`api_key`、`authorization`、`token`、`password` 等
- 环境变量配置加载，使用 `pydantic-settings`
- `ENCRYPTION_KEY` 启动校验：必须是 base64 编码后的 32 字节密钥
- PostgreSQL async session
- Alembic 数据库迁移
- 初始种子数据脚本：默认 Ollama 模型、通用助手、代码助手

对应工程价值：

- KISS：后端入口、配置、DB session、路由拆分清晰，便于定位问题。
- DRY：traceId、异常响应、日志脱敏集中处理，避免业务接口重复实现。

### 2.2 认证与登录

已具备：

- `POST /v1/auth/login` 登录接口
- 登录成功返回 JWT token
- 默认 `AUTH_DISABLED=false`，业务接口需要有效 Bearer Token
- `AUTH_DISABLED=true` 仅用于本地开发，任意用户名和密码可登录，返回匿名 token
- 前端登录页会保存 token 到 `localStorage`
- 前端 API 请求会附带 `Authorization: Bearer <token>`

部分实现：

- 后端已经有 `require_auth` 和 `require_public_identity` 依赖，支持 JWT 与外部 API Key 两类身份。
- Chat 与 Process 同时兼容管理员 JWT 和外部 API Key。

建议：

- 真实使用环境必须保持 `AUTH_DISABLED=false`，并设置非默认 `AUTH_USERNAME`、`AUTH_PASSWORD` 和独立 `JWT_SECRET`。
- 登录能力保留为单用户模式，符合当前 MVP 的 KISS/YAGNI 边界。

### 2.3 模型配置管理

后端已具备：

| 能力 | 接口 |
|------|------|
| 列出模型配置 | `GET /v1/models` |
| 创建模型配置 | `POST /v1/models` |
| 获取模型详情 | `GET /v1/models/{id}` |
| 更新模型配置 | `PUT /v1/models/{id}` |
| 删除模型配置 | `DELETE /v1/models/{id}` |
| 检测模型连通性 | `GET /v1/models/{id}/ping` |
| 查询 Provider 下可用模型 | `GET /v1/models/{id}/list` |

已支持的 Provider：

- `ollama`
- `openai-compatible`

模型管理特性：

- 模型配置存储在 PostgreSQL `models` 表
- API Key 使用 AES-256-GCM 加密后入库
- API Key 返回给前端时只展示脱敏结果
- 配置创建、更新、删除后会重建 ProviderRegistry 快照
- 支持模型别名 `aliases`
- 支持 provider 连通性检测和远端模型列表查询

前端已具备：

- 模型列表展示
- 新增模型配置
- 删除模型配置
- Ping 连通性检测
- 展示 provider、model、baseUrl、别名和脱敏 API Key

部分实现：

- 后端支持模型更新，前端当前没有完整编辑表单。
- 后端支持 Provider 子模型列表，前端当前没有入口展示。
- 架构文档提到的故障转移、负载均衡暂未实现。

### 2.4 Provider 适配层

已具备：

- `BaseProvider` 抽象接口
- `OllamaProvider`
- `OpenAICompatibleProvider`
- `ProviderRegistry`
- 模型 ID 和别名解析
- Provider health check
- Provider model list
- Provider 流式 chat 输出转换为统一 `ChatChunk`

Provider 行为：

- Ollama 调用 `/api/chat` 和 `/api/tags`
- OpenAI 兼容 Provider 调用 `/v1/chat/completions` 和 `/v1/models`
- OpenAI 兼容 Provider 可覆盖 OpenAI、DeepSeek、Groq 等兼容接口

部分实现：

- Provider 基类有 `abort` 抽象能力，但当前 chat 中断主要由 Chat API 的内存事件控制。
- Anthropic、Qwen、任意自定义 HTTP 适配不在当前实现内。

### 2.5 Chat 对话能力

后端已具备：

| 能力 | 接口 |
|------|------|
| OpenAI 风格对话 | `POST /v1/chat/completions` |
| 流式 SSE 响应 | `POST /v1/chat/completions`，`stream=true` |
| 非流式响应 | `POST /v1/chat/completions`，`stream=false` |
| 取消流式请求 | `DELETE /v1/chat/{stream_id}` |
| 用量统计 | `GET /v1/chat/stats` |

对话特性：

- 请求体兼容 OpenAI Chat Completions 的核心字段：`model`、`messages`、`stream`、`temperature`、`max_tokens`、`top_p`、`stop`
- 流式响应通过 `data: ...` SSE 格式返回
- 流式响应头返回 `X-Stream-Id`
- 非流式响应返回完整 assistant 内容
- 对话完成后保存到 `conversations` 表
- 对话记录保存 token usage 和 provider latency
- 用量统计支持按模型、按日期聚合

前端已具备：

- Chat 页面
- 模型选择
- 消息输入和发送
- 流式输出逐步渲染
- 停止生成按钮
- 可选择提示词模板并填写变量

部分实现：

- 前端停止生成当前只中断浏览器 fetch，没有调用 `DELETE /v1/chat/{stream_id}` 通知后端取消。
- 前端对话中的提示词模板只注入 `system`，没有使用后端 `PromptEngine` 渲染完整 `user_template`。
- 后端保存了对话记录，但当前没有对话历史列表和加载历史的 API/UI。
- 当前 SSE 使用 FastAPI `StreamingResponse` 手写格式；架构文档规划的是 `sse-starlette`。

### 2.6 提示词模板管理

后端已具备：

| 能力 | 接口 |
|------|------|
| 列出提示词 | `GET /v1/prompts` |
| 按标签过滤 | `GET /v1/prompts?tag=xxx` |
| 按名称搜索 | `GET /v1/prompts?search=xxx` |
| 创建提示词 | `POST /v1/prompts` |
| 获取提示词详情 | `GET /v1/prompts/{id}` |
| 更新提示词 | `PUT /v1/prompts/{id}` |
| 删除提示词 | `DELETE /v1/prompts/{id}` |
| 渲染预览 | `POST /v1/prompts/{id}/render` |
| 查看版本历史 | `GET /v1/prompts/{id}/versions` |
| 回滚到历史版本 | `POST /v1/prompts/{id}/rollback/{version}` |

提示词特性：

- 支持 `system` 和 `user_template`
- 支持 `{{variable}}` 变量插值
- 支持 `{{variable|default}}` 默认值
- 支持缺失变量校验
- 更新提示词时自动保存版本快照
- 支持历史版本回滚
- 支持标签 `tags`

前端已具备：

- 提示词列表
- 新建提示词入口
- 模板编辑器
- 变量自动识别
- 渲染预览
- 版本历史查看
- 历史版本恢复
- 删除提示词

当前限制：

- 前端提示词保存调用的是 `POST /v1/prompts/{id}`，后端实际更新接口是 `PUT /v1/prompts/{id}`，需要修正后编辑保存才能稳定可用。
- 前端创建表单目前偏轻量，完整模板内容主要依赖后续编辑流程。

### 2.7 外部处理接口

已具备：

- `POST /v1/process`
- 输入 `text`、`prompt_id`、`model`、`variables`
- 后端加载提示词模板
- 合并 `text` 和额外变量
- 校验模板必填变量
- 渲染 system/user prompt
- 调用指定模型
- 返回处理结果、模型 ID、提示词 ID、耗时

适用场景：

- 外部系统希望把“文本 + 提示词模板 + 模型”封装成一次处理调用。
- 例如翻译、分类、摘要、代码生成等固定提示词流程。

当前限制：

- 暂不具备真正流式处理能力，只支持同步返回完整结果。
- 当前没有专门的 Pydantic 请求/响应 schema，入参仍是 `dict[str, Any]`。

### 2.8 数据持久化能力

已具备表结构：

| 表 | 用途 |
|----|------|
| `models` | 模型 Provider 配置 |
| `prompts` | 提示词模板 |
| `prompt_versions` | 提示词历史版本快照 |
| `conversations` | 对话消息、用量、耗时 |

数据库能力：

- 使用 JSONB 存储默认参数、变量定义、消息列表、元数据、用量信息
- `prompts.tags` 使用 GIN 索引
- `conversations.model_id`、`conversations.created_at` 有索引
- PostgreSQL trigger 自动维护 `updated_at`
- `prompt_versions` 对 `prompts` 使用级联删除

### 2.9 Web UI 能力

已具备页面：

| 页面 | 路径 | 当前能力 |
|------|------|----------|
| 登录页 | 登录态缺失时显示 | 登录并保存 token |
| Chat | `/chat` | 模型选择、提示词选择、流式对话、停止前端请求 |
| Models | `/models` | 模型列表、新增、删除、Ping |
| Prompts | `/prompts` | 提示词列表、编辑器、变量预览、版本历史、回滚、删除 |

当前 UI 定位：

- 适合作为本地调试和管理界面
- 已覆盖 MVP 主链路
- 尚未达到完整产品化管理后台水平

---

## 3. 规划中或暂不具备能力

当前暂不具备：

- 多用户系统和用户权限模型
- 业务 API 强制鉴权
- Anthropic Provider
- Qwen Provider
- 任意 HTTP 请求格式自定义 Provider
- Provider 故障转移和负载均衡
- 请求队列和后台任务系统
- RAG 知识库
- Function Calling
- Agent 工作流
- 对话历史列表、搜索、详情加载
- 用量统计 Dashboard
- API Key 轮换 UI
- 前后端 OpenAPI 类型自动生成闭环
- 完整生产安全配置，如限流、严格 CORS、CSRF 策略、审计日志

---

## 4. 当前主要风险与完善建议

### P0：生产环境必须禁用无认证模式

现状：

- 代码默认 `AUTH_DISABLED=false`，`.env.example` 也默认启用认证。
- 本地仍可显式设置 `AUTH_DISABLED=true` 跳过认证。

建议：

- 生产部署检查 `AUTH_DISABLED=false`。
- 设置非默认 `AUTH_USERNAME` / `AUTH_PASSWORD`。
- 设置独立强随机 `JWT_SECRET`，不要依赖 `ENCRYPTION_KEY` 兜底。

### 已修复：提示词编辑保存接口方法不一致

现状：

- 后端更新提示词使用 `PUT /v1/prompts/{id}`。
- 前端编辑保存已改为 `apiPut` 调用 `PUT /v1/prompts/{id}`。
- 前端删除提示词已改为复用 `apiDelete`，会带上 Bearer Token。

建议：

- 后续补充前端交互测试，覆盖 Prompt 保存和删除。

### ~~P1：`/v1/process` 文档和实现对 stream 的语义不一致~~

已修复：stream 参数已从代码和文档中移除。

建议：

- 短期：文档移除 `stream` 或标注暂不支持。
- 中期：如确有外部流式处理需求，再实现 SSE。

### P2：Chat 停止生成只停前端连接

现状：

- 后端提供 `DELETE /v1/chat/{stream_id}`。
- 前端未读取 `X-Stream-Id` 并调用取消接口。

建议：

- 前端读取 `X-Stream-Id` 响应头。
- 点击 Stop 时同时 abort fetch 和调用后端取消接口。

### P2：API 文档与实现需要持续同步

现状：

- `docs/2026-06-02-api-usage.md` 只覆盖常用接口，不是完整接口。
- 部分响应示例与实际字段不完全一致。

建议：

- 将人工 API 文档定位为“使用指南”。
- 完整接口以 FastAPI `/docs` 和 OpenAPI schema 为准。

---

## 5. 原则评估

### KISS

当前系统核心链路清晰：模型配置 → ProviderRegistry → Chat API → Web UI。建议继续保持简单实现，先修鉴权和接口不一致，不急于引入复杂 Provider DSL、队列、负载均衡。

### YAGNI

Anthropic、Qwen、RAG、Agent、故障转移等能力已经在规划中，但当前不应阻塞 MVP。`/v1/process` 的流式能力如果没有明确调用方，应先不实现。

### SOLID

Provider 抽象、PromptEngine、KeyManager、API 路由分层基本合理。需要加强的是鉴权横切能力，应通过依赖或 router-level dependency 注入，而不是散落在 handler 内。

### DRY

traceId、错误结构、日志脱敏、KeyManager 已经集中化。后续应避免前端重复实现提示词渲染逻辑，建议统一调用后端 PromptEngine 或生成共享规则。

---

## 6. 推荐下一步

优先级建议：

1. 修复业务 API 鉴权接入。
2. 修复前端提示词更新使用 `PUT`。
3. 修复 Chat Stop，接入 `X-Stream-Id` 和后端取消接口。
4. 更新 `docs/2026-06-02-api-usage.md`，明确它是常用 API 使用指南。
5. 补充快速启动步骤：生成 `ENCRYPTION_KEY`、启动 PostgreSQL、执行迁移、执行 seed、启动后端。
6. 为模型、提示词、Chat 主链路补 API 集成测试。

整体判断：

PandaMind 当前已经具备 MVP 主链路雏形：模型配置、Provider 调用、流式对话、提示词模板、Web UI、数据库持久化都已成型。进入更真实的使用前，最需要补的是鉴权生效、前后端接口一致性和文档同步。
