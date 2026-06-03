# 任务调度 API 调用示例

> 文档生成时间：2026-06-03

---

## 接口信息

- **URL**: `POST http://localhost:8000/v1/process`
- **Content-Type**: `application/json`
- **认证**: 当 `AUTH_DISABLED=true` 时无需认证

---

## Curl 请求示例

```bash
curl -s -X POST http://localhost:8000/v1/process \
  -H "Content-Type: application/json" \
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

---

## 返回结果

```json
{
  "result": "After analyzing the task data, I've planned the most efficient route...",
  "model": "ollama-llama3-default",
  "prompt_id": "task-scheduler",
  "latency_ms": 15565
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
      "tasks": ["客户1", "客户2"],
      "commute": {
        "from": null,
        "to": null,
        "distance_km": 0,
        "duration_hours": 0
      },
      "work_hours": 8,
      "commute_hours": 0,
      "total_hours": 8
    },
    {
      "day": 2,
      "city": "上海",
      "tasks": ["客户3"],
      "commute": {
        "from": "北京",
        "to": "上海",
        "distance_km": 1200,
        "duration_hours": 20
      },
      "work_hours": 8,
      "commute_hours": 2.67,
      "total_hours": 10.67
    },
    {
      "day": 3,
      "city": "上海",
      "tasks": ["客户4"],
      "commute": {
        "from": null,
        "to": null,
        "distance_km": 0,
        "duration_hours": 0
      },
      "work_hours": 8,
      "commute_hours": 0,
      "total_hours": 8
    },
    {
      "day": 4,
      "city": "广州",
      "tasks": ["客户5"],
      "commute": {
        "from": "上海",
        "to": "广州",
        "distance_km": 1400,
        "duration_hours": 23.33
      },
      "work_hours": 8,
      "commute_hours": 2.92,
      "total_hours": 10.92
    }
  ]
}
```

---

## 行程说明

| 天数 | 城市 | 任务 | 说明 |
|------|------|------|------|
| Day 1 | 北京 | 客户1、客户2 | 同一城市合并 |
| Day 2 | 上海 | 客户3 | 跨城市移动 |
| Day 3 | 上海 | 客户4 | 同一城市继续 |
| Day 4 | 广州 | 客户5 | 跨城市移动 |

---

## 注意事项

1. **JSON 格式**：`tasks_json` 必须是单行 JSON 字符串，不能包含换行符
2. **转义字符**：JSON 字符串中的双引号需要转义（`\"`）
3. **演示用途**：当前为演示场景，约束条件（每天≤8小时）可能未完全满足
