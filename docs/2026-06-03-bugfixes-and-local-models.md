# 2026-06-03 — Bug Fixes & 本地模型配置

> 更新日期：2026-06-03

---

## 1. 变更概述

本次变更修复了前端/后端 5 个已知问题，优化了 Admin API 输入校验，并在 seed 数据中新增本地推荐模型配置。

---

## 2. Bug 修复

### P1：前端提示词编辑 HTTP 方法错误

**问题**：`PromptsPage.tsx:142` 用 `apiPost` 保存编辑，后端期望 PUT，返回 405。
**修复**：改为 `apiPut`，与后端 `PUT /v1/prompts/{id}` 对齐。

### P1：前端提示词删除缺少 Authorization

**问题**：删除用原生 fetch，`AUTH_DISABLED=false` 时返回 401。
**修复**：复用 `apiDelete` 封装，自动携带 Bearer Token；删除后清空编辑器状态并刷新列表。

### P1：生产安全配置容易误用为无认证模式

**问题**：`AUTH_DISABLED` 默认 `true`，README 未强制说明生产需关闭。
**修复**：
- `config.py` 默认改为 `False`
- `README.md` Production 段明确要求 `AUTH_DISABLED=false` + 强密码

### P2：Admin API 输入校验偏弱

**问题**：`api_clients.py` / `models.py` 接收 `dict[str, Any]`，缺字段会 KeyError，枚举字段无约束。
**修复**：
- `models.py` 新增 `ModelCreate` / `ModelUpdate` Pydantic schema，provider 枚举校验
- `ModelUpdate` 中 `name/provider/model/default_params/aliases/enabled` 显式传 null 时返回 422，只允许 `base_url`/`api_key` 清空为 null
- `api_clients.py` 已有 `ApiClientCreate` / `ApiKeyCreate` schema（此前已存在）

### P2：`/v1/process` stream 参数语义不完整

**问题**：读取 `stream` 参数但无论真假都聚合完整响应返回 JSON。
**修复**：移除 `stream` 参数及文档说明，避免误导。

---

## 3. 安全加固

### model update 支持显式 null

**问题**：`update_model` 用 `data.xxx is not None` 判断，客户端传 `{"api_key": null}` 无法清空旧密钥。
**修复**：改用 `data.model_dump(exclude_unset=True)` 区分"未传"和"显式传 null"。

### ALLOWED_PROVIDERS 收紧

**问题**：允许 `anthropic` / `qwen` / `custom`，但对应 Provider 未实现，创建后 registry 静默跳过。
**修复**：限制为 `{"ollama", "openai-compatible"}`，等实现后再放开。

---

## 4. 本地模型 Seed 数据

`seed.py` 新增两个推荐模型配置，需手动执行写入数据库（不会在启动时自动执行）：

```bash
PYTHONPATH=src uv run python -m pandamind.db.seed
```

| 模型 | alias | 用途 |
|------|-------|------|
| `qwen3:8b` | `qwen`, `daily` | 日常对话、代码、翻译，综合能力最强 |
| `deepseek-r1:14b` | `reasoning`, `algorithm` | 算法推理专用，链式思考能力突出 |

**使用前需先下载模型**：
```bash
ollama pull qwen3:8b
ollama pull deepseek-r1:14b
```

**推荐配置**（针对 M2 Pro 16GB）：
- 日常使用 `qwen3:8b`（~30-40 token/s）
- 算法推理用 `deepseek-r1:14b`（~10-15 token/s，推理质量高）

---

## 5. 变更文件清单

| 文件 | 变更 |
|------|------|
| `apps/web/src/pages/PromptsPage.tsx` | P1: apiPost→apiPut，删除增加 auth/refresh |
| `apps/server/src/pandamind/api/models.py` | P2: Pydantic schema，provider 枚举，null 处理 |
| `apps/server/src/pandamind/api/process.py` | P2: 移除 stream 参数 |
| `apps/server/src/pandamind/core/config.py` | P3: auth_disabled 默认 False |
| `apps/server/.env.example` | P3: 默认 AUTH_DISABLED=false |
| `apps/server/README.md` | P3: 生产文档明确要求关闭 AUTH_DISABLED |
| `apps/server/src/pandamind/db/seed.py` | 新增 qwen3:8b / deepseek-r1:14b |
