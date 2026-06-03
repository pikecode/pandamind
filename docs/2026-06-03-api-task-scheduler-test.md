# 2026-06-03 — 外部 API 调用任务调度场景测试

> 更新日期：2026-06-03

---

## 测试目标

验证外部 API 调用 `/v1/process` 接口，使用 `task-scheduler` 提示词模板完成多城市施工任务调度规划。

## 前置条件

- 后端服务运行（`http://localhost:8000`）
- 管理员 JWT Token（用于创建 Client/Key）
- `task-scheduler` 提示词模板已 seed

## 测试步骤

### 1. 创建外部 API Client

```bash
curl -s -X POST http://localhost:8000/v1/api-clients \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ADMIN_JWT>" \
  -d '{"name":"test-client"}'
```

**返回**：
```json
{
  "id": "v-k-azyOEbDTAiuEjjfkv",
  "name": "test-client",
  "status": "active"
}
```

### 2. 创建 API Key

```bash
curl -s -X POST http://localhost:8000/v1/api-clients/v-k-azyOEbDTAiuEjjfkv/keys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ADMIN_JWT>" \
  -d '{
    "name": "test-key",
    "scopes": ["chat:invoke", "process:invoke", "models:list", "prompts:list"]
  }'
```

**返回**：
```json
{
  "id": "lbbM8qlFirc5G1qclbLdp",
  "api_key": "pmk_live_6ciVdxITIJJSk9XzCStNg_oZTta730Cvp3E8K6sLeCFheT8Q-O4RfL49gIbLQlAY8"
}
```

### 3. 调用任务调度接口

```bash
curl -s -X POST http://localhost:8000/v1/process \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer pmk_live_6ciVdxITIJJSk9XzCStNg_oZTta730Cvp3E8K6sLeCFheT8Q-O4RfL49gIbLQlAY8" \
  -d '{
    "text": "start_city=北京, speed=60",
    "prompt_id": "task-scheduler",
    "variables": {
      "start_city": "北京",
      "speed_km_per_hour": "60",
      "tasks": "5个客户任务",
      "tasks_json": "[{\"customer\":\"客户1\",\"factory\":\"工厂A\",\"city\":\"北京\",\"duration_hours\":10},{\"customer\":\"客户2\",\"factory\":\"工厂B\",\"city\":\"北京\",\"duration_hours\":20},{\"customer\":\"客户3\",\"factory\":\"工厂C\",\"city\":\"上海\",\"duration_hours\":15},{\"customer\":\"客户4\",\"factory\":\"工厂D\",\"city\":\"上海\",\"duration_hours\":25},{\"customer\":\"客户5\",\"factory\":\"工厂E\",\"city\":\"广州\",\"duration_hours\":8}]"
    }
  }'
```

### 4. 预期返回

```json
{
  "result": "After analyzing the tasks...",
  "model": "ollama-llama3-default",
  "prompt_id": "task-scheduler",
  "latency_ms": 1234
}
```

其中 `result` 包含 JSON 格式的行程规划：

```json
{
  "total_days": 4,
  "days": [
    {
      "day": 1,
      "city": "北京",
      "tasks": ["客户1"],
      "commute": {
        "from": "北京",
        "to": "北京",
        "distance_km": 0,
        "duration_hours": 0
      },
      "work_hours": 8,
      "commute_hours": 0,
      "total_hours": 8
    }
  ]
}
```

## 关键参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `prompt_id` | string | 固定值 `task-scheduler` |
| `variables.start_city` | string | 工人出发城市 |
| `variables.speed_km_per_hour` | string | 通勤速度（km/h） |
| `variables.tasks` | string | 任务描述 |
| `variables.tasks_json` | string | 任务数据 JSON 字符串 |

## 任务数据结构

```json
[
  {"customer": "客户1", "factory": "工厂A", "city": "北京", "duration_hours": 10},
  {"customer": "客户2", "factory": "工厂B", "city": "北京", "duration_hours": 20},
  {"customer": "客户3", "factory": "工厂C", "city": "上海", "duration_hours": 15},
  {"customer": "客户4", "factory": "工厂D", "city": "上海", "duration_hours": 25},
  {"customer": "客户5", "factory": "工厂E", "city": "广州", "duration_hours": 8}
]
```

## 测试结果

| 步骤 | 状态 | 耗时 |
|------|------|------|
| 创建 Client | 成功 | ~50ms |
| 创建 API Key | 成功 | ~50ms |
| 调用 Process | 成功 | ~8s（模型生成） |
| 缓存命中 | 成功 | ~1s（第二次调用） |

## 注意事项

1. **API Key 有效期**：默认无过期时间，生产环境建议设置 `expires_at`
2. **Scope 校验**：API Key 必须有 `process:invoke` scope 才能调用 `/v1/process`
3. **模型缓存**：相同输入 5 分钟内直接返回缓存结果
4. **城市距离**：当前模型不计算实际距离，通勤时间需外部提供

## 已知限制

- 模型不计算城市间实际距离，通勤时间为简化估算
- 每天 8 小时上限包含施工 + 通勤，但模型可能不完全遵守
- 输出 JSON 需要前端解析，可能包含 markdown 代码块
