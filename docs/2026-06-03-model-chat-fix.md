# 2026-06-03 — 模型对话修复记录

> 更新日期：2026-06-03

---

## 问题描述

前端 Chat 页面模型下拉框为空，选择模型后对话无回复。

## 根因分析

1. **seed ID 超长**：`ollama-deepseek-r1-14b` 实际 22 字符，超过数据库 `models.id` 字段 `VARCHAR(21)` 限制，导致 seed 插入失败
2. **数据库端口混乱**：开发过程中 `.env` 临时改为 5433，但 docker-compose.dev.yml 仍是 5432，seed 数据写入 5433 而后端连接 5432
3. **Registry 未重建**：后端启动时从数据库加载模型到内存 Registry，旧数据库缺少新模型
4. **Ollama 模型缺失**：本地未下载 `qwen3:8b` 和 `deepseek-r1:14b`

## 修复过程

### 1. 修复 seed ID 长度

```python
# 修改前（22 字符，插入失败）
"id": "ollama-deepseek-r1-14b"

# 修改后（9 字符，正常插入）
"id": "ds-r1-14b"
```

### 2. 统一数据库端口

```bash
# 恢复 .env 端口
DATABASE_URL=postgresql://pandamind:pandamind@localhost:5432/pandamind
```

### 3. 重新 seed 并重启后端

```bash
cd apps/server
PYTHONPATH=src uv run python -m pandamind.db.seed

# 重启后端加载新模型
pkill -f "uvicorn pandamind.main:app"
PYTHONPATH=src uv run uvicorn pandamind.main:app --host 127.0.0.1 --port 8000
```

### 4. 下载 Ollama 模型

```bash
ollama pull qwen3:8b         # 5.2 GB
ollama pull deepseek-r1:14b  # 9.0 GB
```

## 验证结果

```bash
curl -s http://localhost:8000/v1/models -H "Authorization: Bearer test"
# 返回 4 个模型：
# - Local Llama 3 (Ollama)
# - Test OpenAI
# - Local Qwen3 8B (Ollama)
# - Local DeepSeek R1 14B (Ollama)

curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test" \
  -d '{"model":"ollama-qwen3-8b","messages":[{"role":"user","content":"你好"}]}'
# 返回：你好呀！😊 今天有什么想聊的
```

## 教训

1. **数据库字段长度**：自定义 ID 必须严格检查长度，不能依赖目测
2. **端口一致性**：修改开发端口后要同步所有配置文件
3. **Registry 重建**：修改模型数据后必须重启后端
4. **模型预下载**：Ollama 模型需提前下载，不能依赖运行时自动拉取
