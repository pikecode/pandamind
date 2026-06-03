# PandaMind — 开发计划

> 版本：v0.4
> 更新：2026-06-01

**v0.4 重大变更**：后端从 Node.js + Fastify 切换为 Python 3.11+ + FastAPI，详见 architecture.md ADR-009。

---

## 总体原则

- 每个 Milestone 交付可运行的版本，不做半成品
- 先跑通核心链路，再补完整功能
- 每个任务完成后写对应测试，不攒到最后

---

## Milestone 1 — 项目骨架 + 基础设施

**目标**：本地能跑起来，PostgreSQL 连通，前后端联调通

### M1.1 项目结构初始化
- [ ] 顶层目录：`apps/server`（Python 后端）、`apps/web`（React 前端）、`docs/`
- [ ] 前端 monorepo：`pnpm-workspace.yaml` 仅含 `apps/web`
- [ ] 后端 Python：`apps/server/pyproject.toml`（uv 管理）
- [ ] 根目录 `package.json` 暂只管前端脚本，后端脚本在 `apps/server/` 内独立运行
- [ ] `tsconfig.base.json`（前端继承用）
- [ ] Vitest 前端测试配置（仅前端；后端 Python 测试由 pytest + pytest-asyncio + httpx.AsyncClient 覆盖，配置在 `apps/server/pyproject.toml` 的 `[project.optional-dependencies] dev` 组）

### M1.2 后端依赖与配置
- [ ] `apps/server/pyproject.toml` 依赖：fastapi、uvicorn[standard]、pydantic、pydantic-settings、sqlalchemy[asyncio]、asyncpg、alembic、httpx、structlog、cryptography、nanoid、sse-starlette、slowapi、python-multipart、pytest、pytest-asyncio
- [ ] `apps/server/.env.example`：DATABASE_URL、ENCRYPTION_KEY、LOG_LEVEL、ALLOWED_ORIGINS
- [ ] `apps/server/src/pandamind/core/config.py`：用 `pydantic-settings` 加载环境变量
- [ ] 启动时校验 `ENCRYPTION_KEY` 存在且 `base64.b64decode` 后必须等于 32 字节，否则拒绝启动
- [ ] `uv sync` 验证依赖锁定

### M1.3 数据库基础设施
- [ ] `docker-compose.dev.yml`：只启动 PostgreSQL（开发用）
- [ ] `docker-compose.yml`：完整服务（PostgreSQL + server + web）
- [ ] SQLAlchemy 2.0 async 接入，`apps/server/src/pandamind/db/session.py` 提供 async session
- [ ] `apps/server/src/pandamind/db/models.py`：ORM 模型（`models` / `prompts` / `prompt_versions` / `conversations`）
- [ ] Alembic 初始化（`alembic.ini` + `alembic/env.py` 配 async engine）
- [ ] 首次迁移文件：建表 + `updated_at` 自动更新触发器 + GIN 索引
- [ ] `apps/server/src/pandamind/db/seed.py`：写入示例模型配置（Ollama llama3）和示例提示词模板（通用助手、代码助手）

### M1.4 后端框架搭建
- [ ] FastAPI 初始化，`apps/server/src/pandamind/main.py` 入口
- [ ] 注册 CORS 中间件（基于 `ALLOWED_ORIGINS`）、SlowAPI 限流、structlog 日志
- [ ] `GET /health` 健康检查端点
- [ ] 全局异常处理：统一 `{ code, message, details, traceId }` 格式，details 不暴露密钥
- [ ] traceId 中间件：每个请求生成 nanoid，注入 `X-Trace-Id` 响应头，绑定到 structlog 日志上下文（服务端生成，不信任客户端传入）
- [ ] DB session 依赖注入（`Depends(get_session)`）

### M1.5 前端框架搭建
- [ ] `apps/web` 内 `package.json` + Vite + React + TypeScript
- [ ] Tailwind CSS + shadcn/ui 接入
- [ ] 路由配置（React Router）：`/chat`、`/prompts`、`/models`
- [ ] API 客户端封装（`lib/api.ts`，基于 fetch；统一读取响应头 `X-Trace-Id` 和 `X-Stream-Id`，用于错误提示和调试，不在客户端生成任何 ID）
- [ ] OpenAPI 类型生成配置：根目录脚本 `pnpm gen:api` 调 `openapi-typescript` 从后端 `/openapi.json` 生成到 `apps/web/src/lib/api-types.ts`；要求：开发时先 `uv run uvicorn` 启动后端，再跑 `pnpm gen:api`；M1.5 验收时需后端在线
- [ ] 基础布局组件（侧边栏导航 + 主内容区）

**验收标准**：`uv run uvicorn` 启动后端（端口 8000），`pnpm dev` 启动前端（端口 5173），浏览器访问前端页面，`/health` 返回 200，数据库表已创建。

---

## Milestone 2a — 核心 Provider + 模型管理

**目标**：跑通 Ollama 和 OpenAI 兼容接口，可通过 UI 管理模型配置

### M2a.1 Provider Adapter 层（MVP）
- [ ] 定义 `BaseProvider` 抽象类（`providers/base.py`），含 `chat` / `abort` / `health_check` / `list_models`
- [ ] 实现 `OllamaProvider`（chat 流式 + abort + health_check + list_models）
- [ ] 实现 `OpenAICompatibleProvider`（兼容所有 OpenAI 格式接口，含 abort）— 同时覆盖 OpenAI、DeepSeek、Groq 等
- [ ] `ProviderRegistry`：启动时加载数据库配置，实例化并注册 Provider；配置更新后重建快照（不做细粒度热替换）
- [ ] **单元测试**：mock httpx 响应，覆盖 chat 流式、health_check 成功/失败、abort 场景

### M2a.2 Key Manager
- [ ] AES-256-GCM 加密/解密工具函数（`services/key_manager.py`）
- [ ] 写入时加密，读取时解密，UI 展示只显示末 4 位
- [ ] structlog 处理器：自动脱敏 `api_key`、`authorization` 字段，不明文写入日志
- [ ] **单元测试**：加密/解密往返、脱敏展示

### M2a.3 模型管理 API
- [ ] `GET /v1/models` — 列出数据库中的模型配置（脱敏 apiKey）
- [ ] `POST /v1/models` — 创建模型配置（apiKey 加密存储）
- [ ] `GET /v1/models/{id}` — 详情
- [ ] `PUT /v1/models/{id}` — 更新（触发 ProviderRegistry 重建）
- [ ] `DELETE /v1/models/{id}` — 删除
- [ ] `GET /v1/models/{id}/ping` — 连通性检测
- [ ] `GET /v1/models/{id}/list` — 动态查询 Provider 下可用子模型
- [ ] Pydantic schema 定义在 `schemas/model.py`，OpenAPI 自动暴露

### M2a.4 模型管理 UI
- [ ] 模型列表页（显示 Provider 类型、连通状态、别名）
- [ ] 新建/编辑模型表单（Provider 类型选择、参数配置）
- [ ] Ping 按钮 + 连通状态展示（绿/红/loading）
- [ ] apiKey 输入框（输入时隐藏，展示时脱敏）

**验收标准**：UI 中添加 Ollama 模型配置，点击 Ping 返回成功；添加 OpenAI 兼容配置（如 DeepSeek），Ping 成功。

---

## Milestone 2b — 扩展 Provider（非 MVP，按需推进）

**目标**：支持 Anthropic、通义千问、自定义 OpenAI 兼容 Provider

### M2b.1 扩展 Provider 实现
- [ ] 实现 `AnthropicProvider`（含 abort，处理 Anthropic 特有格式转换）
- [ ] 实现 `QwenProvider`（通义千问 API）
- [ ] 实现 `CustomProvider`（用户配置 baseUrl + API Key + 默认参数，适配 OpenAI 兼容接口，不做请求格式配置）
- [ ] **单元测试**：各 Provider mock 响应覆盖

**验收标准**：UI 中添加 Anthropic 模型配置，对话正常返回流式输出。

---

## Milestone 3 — 对话核心

**目标**：可以通过 UI 与模型对话，支持流式输出

### M3.1 Model Router
- [ ] `ModelRouter` 服务：解析 `provider/model` 格式，分发到对应 Provider
- [ ] 别名解析（从数据库 `aliases` 字段查找）
- [ ] Provider 不可用时返回明确错误

### M3.2 Chat API
- [ ] `POST /v1/chat/completions`（OpenAI 兼容格式）
- [ ] 每次流式请求生成 `streamId`（nanoid），SSE 首帧携带，响应头 `X-Stream-Id` 返回给客户端；每个请求生成 `traceId`，响应头 `X-Trace-Id` 返回，绑定到 structlog 日志上下文（服务端生成，不信任客户端传入）
- [ ] 流式响应（`sse-starlette` 的 `EventSourceResponse`，`data: {...}\n\n` 格式；不要裸用 FastAPI `StreamingResponse` 手写 SSE）
- [ ] 非流式响应（等待完整结果返回）
- [ ] `DELETE /v1/chat/{streamId}` — 客户端用 streamId 中止进行中的流式生成
- [ ] 请求参数合并（请求参数 > 模型默认参数）
- [ ] 对话历史自动保存到 `conversations` 表，title 取首条用户消息前 50 字

### M3.3 对话 UI
- [ ] 对话界面（消息列表 + 输入框）
- [ ] 流式输出渲染（逐 token 显示）
- [ ] 模型选择下拉（从 `/v1/models` 加载）
- [ ] 停止生成按钮（中断 SSE 连接 + 调用 `DELETE /v1/chat/{streamId}`）
- [ ] Markdown 渲染（代码块高亮）
- [ ] 对话历史侧边栏（列表 + 点击加载）

**验收标准**：选择 Ollama 模型，发送消息，看到流式输出；历史记录可查看。

---

## Milestone 4 — 提示词管理

**目标**：可以创建、编辑提示词模板，并在对话中使用

### M4.1 Prompt Engine
- [ ] `PromptEngine` 服务：`{{variable}}` 变量插值渲染
- [ ] 渲染时合并 system prompt + user template + 用户消息
- [ ] 必填变量校验（缺失时返回 400 + 缺失字段列表）

### M4.2 提示词版本管理
- [ ] 更新模板时自动写入 `prompt_versions` 快照
- [ ] `GET /v1/prompts/{id}/versions` — 版本历史列表
- [ ] `POST /v1/prompts/{id}/rollback/{ver}` — 回滚到指定版本

### M4.3 提示词 API
- [ ] `GET /v1/prompts` — 列表（支持 `?tag=&search=` 过滤）
- [ ] `POST /v1/prompts` — 创建
- [ ] `GET /v1/prompts/{id}` — 详情
- [ ] `PUT /v1/prompts/{id}` — 更新（触发版本快照）
- [ ] `DELETE /v1/prompts/{id}` — 删除
- [ ] `POST /v1/prompts/{id}/render` — 渲染预览

### M4.4 提示词 UI
- [ ] 模板列表页（卡片展示，标签过滤，搜索）
- [ ] 模板编辑器（system / user template 分区编辑）
- [ ] 变量定义面板（名称、描述、默认值、是否必填）
- [ ] 渲染预览面板（填入变量值，实时预览渲染结果）
- [ ] 版本历史抽屉（查看历史版本，一键回滚）

### M4.5 对话中使用提示词
- [ ] 对话界面增加"选择提示词模板"入口
- [ ] 选择模板后弹出变量填写表单
- [ ] 渲染后的 system prompt 注入对话请求

**验收标准**：创建含变量的提示词模板，在对话中选用并填入变量，system prompt 正确注入模型。

---

## Milestone 5 — 完善与部署

**目标**：生产可用，一键 Docker 部署

### M5.1 认证系统（已提前实现基础版）
- [x] JWT 认证依赖（自实现 `pyjwt`）
- [x] `POST /v1/auth/login` — 获取 Token（单用户，密码配置在环境变量）
- [x] `AUTH_DISABLED=true` 时跳过认证，仅允许本地开发使用
- [x] 前端登录页 + Token 存储

### M5.2 生产 Docker 配置
- [ ] `apps/server/Dockerfile`（多阶段：uv 装依赖 → 运行时精简镜像）
- [ ] `apps/web/Dockerfile`（Nginx 静态托管）
- [ ] `docker-compose.yml` 完整版（PostgreSQL + server + web + Nginx 反代）
- [ ] 启动脚本自动执行 `alembic upgrade head`

### M5.3 用量统计
- [ ] 对话记录中保存 token 用量、耗时、Provider 来源
- [ ] `GET /v1/stats` — 汇总统计（按模型、按日期）
- [ ] UI Dashboard 展示用量图表

### M5.4 测试补全
- [ ] Prompt Engine 单元测试（变量插值、缺失校验、模板组合）
- [ ] Key Manager 单元测试（加密/解密往返、脱敏展示）
- [ ] Model Router 单元测试（前缀路由、别名解析、Provider 不可用）
- [ ] API 集成测试（chat、models、prompts 主要端点 happy path + error case）
- [ ] 验证整体测试覆盖率 ≥ 80%

### M5.5 文档
- [ ] `README.md` 更新（快速启动、环境变量说明）
- [ ] API 文档（FastAPI `/docs` Swagger UI 自动生成）

**验收标准**：`docker compose up` 一键启动，访问 UI 完成完整对话流程。

---

## 里程碑时间线（参考）

```
M1 骨架基础设施     ████░░░░░░░░░░░░░░░░
M2 模型管理         ░░░░████░░░░░░░░░░░░
M3 对话核心         ░░░░░░░░████░░░░░░░░
M4 提示词管理       ░░░░░░░░░░░░████░░░░
M5 完善部署         ░░░░░░░░░░░░░░░░████
```

每个 Milestone 建议独立分支开发，完成后合并 main。

---

## 开发顺序建议

优先级排序（高 → 低）：

1. **M1 全部** — 没有基础设施，后面都跑不起来
2. **M2a.1 + M2a.2** — Provider 层 + Key Manager 是核心，先跑通 Ollama
3. **M3.1 + M3.2** — Chat API 是主链路
4. **M3.3** — 有 UI 才能直观验证
5. **M2a.3 + M2a.4** — 模型管理 UI
6. **M4 全部** — 提示词是增值功能
7. **M2b** — 扩展 Provider，按需推进
8. **M5 全部** — 最后收尾

---

## 技术风险与应对

| 风险 | 概率 | 应对 |
|------|------|------|
| Ollama 流式 API 格式与 OpenAI 不完全兼容 | 中 | Provider 层做格式转换，不透传原始响应 |
| PostgreSQL JSONB 查询性能 | 低 | 对话历史加索引，Phase 2 前评估是否拆 conversation_messages 表 |
| SSE 在某些反代配置下被缓冲 | 中 | Nginx 配置 `X-Accel-Buffering: no`，文档说明 |
| API Key 加密主密钥丢失 | 低 | 文档强调备份 `ENCRYPTION_KEY`，丢失需重新配置所有 Key |
| streamId → asyncio.Task / httpx stream handle 内存泄漏 | 中 | 流式请求完成/客户端断连时主动清理 Map 条目；asyncio.Task 用 `add_done_callback` 释放；httpx Response 显式 `aclose()`；设置最大并发上限 |
| Pydantic / OpenAPI schema 与前端类型漂移 | 低 | CI 跑 `pnpm gen:api` 校验 diff，任何 schema 变更必须同步前端 |
| Python 依赖体积大、Docker 镜像重 | 中 | 多阶段构建；运行时仅 `uvicorn` + 必要包；目标镜像 < 200MB |

---

## 首版不做清单（v1 明确不实现）

以下能力推迟到 Phase 2 / Phase 3，首版不引入：

- **多用户系统**：v1 单用户，`AUTH_DISABLED=true` 仅本地开发；基础单用户 JWT 已提前实现
- **Anthropic / Qwen / Custom Provider**：M2b 按需推进，不阻塞 MVP
- **Provider 故障转移 / 负载均衡**：Phase 3
- **请求队列（Celery / RQ）**：Phase 3
- **用量统计 Dashboard**：M5.3，不进入 M1-M4
- **RAG 知识库**：Phase 4
- **Function Calling / Agent 工作流**：Phase 4
- **conversation_messages 拆表**：Phase 2 前评估，当前 JSONB 足够
- **细粒度 Provider 热替换**：v1 只做重建 registry 快照
- **API Key 轮换 UI**：M5 安全收尾阶段
- **CORS 生产配置细节**：M5 收尾（基础护栏 ENCRYPTION_KEY 校验、日志脱敏已在 M1/M2a 完成）
