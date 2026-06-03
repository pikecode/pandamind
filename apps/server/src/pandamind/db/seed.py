"""Seed initial example data: one Ollama model + two prompt templates.

Idempotent: skips inserts that would conflict on primary key.
"""
from __future__ import annotations

import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert

from pandamind.db.models import ModelConfig, Prompt
from pandamind.db.session import AsyncSessionLocal

OLLAMA_EXAMPLE_ID = "ollama-llama3-default"
PROMPT_GENERAL_ID = "general-assistant"
PROMPT_CODE_ID = "code-assistant"
PROMPT_SCHEDULER_ID = "task-scheduler"

SEED_MODELS = [
    {
        "id": OLLAMA_EXAMPLE_ID,
        "name": "Local Llama 3 (Ollama)",
        "provider": "ollama",
        "model": "llama3:8b",
        "base_url": "http://127.0.0.1:11434",
        "api_key_enc": None,
        "default_params": {"temperature": 0.7, "max_tokens": 2048},
        "aliases": ["local", "fast"],
        "enabled": True,
    },
    {
        "id": "ollama-qwen3-8b",
        "name": "Local Qwen3 8B (Ollama)",
        "provider": "ollama",
        "model": "qwen3:8b",
        "base_url": "http://127.0.0.1:11434",
        "api_key_enc": None,
        "default_params": {"temperature": 0.7, "max_tokens": 2048},
        "aliases": ["qwen", "daily"],
        "enabled": True,
    },
    {
        "id": "ds-r1-14b",
        "name": "Local DeepSeek R1 14B (Ollama)",
        "provider": "ollama",
        "model": "deepseek-r1:14b",
        "base_url": "http://127.0.0.1:11434",
        "api_key_enc": None,
        "default_params": {"temperature": 0.6, "max_tokens": 4096},
        "aliases": ["reasoning", "algorithm"],
        "enabled": True,
    },
]

SEED_PROMPTS = [
    {
        "id": PROMPT_GENERAL_ID,
        "name": "通用助手",
        "description": "通用对话场景，无领域偏好",
        "system": "你是一个乐于助人的助手，回答简洁准确。",
        "user_template": "{{question}}",
        "variables": [
            {"name": "question", "description": "用户问题", "required": True},
        ],
        "tags": ["general", "starter"],
        "version": 1,
    },
    {
        "id": PROMPT_CODE_ID,
        "name": "代码助手",
        "description": "专注代码生成和调试",
        "system": "你是一个专业的 {{language}} 开发者，擅长 {{specialty}}。回答时给出可运行的代码示例。",
        "user_template": "请帮我 {{task}}",
        "variables": [
            {"name": "language", "description": "编程语言", "default": "TypeScript"},
            {"name": "specialty", "description": "专长领域", "default": "后端开发"},
            {"name": "task", "description": "任务描述", "required": True},
        ],
        "tags": ["code", "dev"],
        "version": 1,
    },
    {
        "id": PROMPT_SCHEDULER_ID,
        "name": "任务调度规划器",
        "description": "为外派工人规划多城市施工任务的最短天数行程，考虑每日8小时工时上限和通勤时间",
        "system": "你是一个严格的任务调度规划专家。你必须遵守所有约束条件，否则规划无效。\n\n## 核心约束（必须严格遵守）\n1. 每天总时间 = 施工时间 + 通勤时间 ≤ 8 小时\n2. 任务不可拆分，必须完整完成（duration_hours 是固定的）\n3. 同一城市多个任务可以合并到同一天，但总和 ≤ 8 小时\n4. 跨城市通勤时间 = 城市间距离 / speed_km_per_hour（北京-上海约 1200km，北京-广州约 2100km，上海-广州约 1400km）\n5. 如果某天包含跨城市通勤，则当天施工时间 = 8 - 通勤时间\n6. 如果通勤时间 > 8 小时，则当天只能通勤，不能施工\n7. 同一城市内通勤时间为 0\n\n## 规划策略\n1. 优先安排同一城市的任务，减少跨城市通勤\n2. 同一城市任务按 duration_hours 从小到大排序，尽量多安排在同一天\n3. 跨城市移动时，如果通勤时间 + 目标城市首个任务 ≤ 8h，可以当天到达并施工\n4. 如果通勤时间 > 8h，需要专门安排一天只通勤\n5. 最后一天不需要返回 start_city\n\n## 输出格式（必须严格返回 JSON）\n```json\n{\n  \"total_days\": <整数>,\n  \"days\": [\n    {\n      \"day\": <整数>,\n      \"city\": \"<当天所在城市>\",\n      \"tasks\": [\"<客户名>\"],\n      \"commute\": {\n        \"from\": \"<出发城市>\",\n        \"to\": \"<到达城市>\",\n        \"distance_km\": <数字>,\n        \"duration_hours\": <数字>\n      },\n      \"work_hours\": <当天施工小时>,\n      \"commute_hours\": <当天通勤小时>,\n      \"total_hours\": <当天总小时>\n    }\n  ]\n}\n```\n\n## 重要提醒\n- 必须验证每天 total_hours ≤ 8\n- 任务 duration_hours 是固定的，不能修改\n- 如果某天只通勤不施工，work_hours = 0\n- 如果某天在同一城市施工，commute = null, commute_hours = 0\n- 请确保输出是有效的 JSON，不要添加注释",
        "user_template": "请为以下任务规划最短总天数的行程。\n\n## 输入参数\n- start_city: {{start_city}}\n- speed_km_per_hour: {{speed_km_per_hour}}\n- tasks: {{tasks}}\n\n## 任务数据\n{{tasks_json}}\n\n请输出 JSON 格式的行程规划。",
        "variables": [
            {"name": "start_city", "description": "工人出发城市", "required": True},
            {"name": "speed_km_per_hour", "description": "通勤速度（公里/小时）", "required": True},
            {"name": "tasks", "description": "任务列表描述", "required": True},
            {"name": "tasks_json", "description": "任务数据的 JSON 字符串", "required": True},
        ],
        "tags": ["scheduler", "planning", "logistics"],
        "version": 1,
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        for row in SEED_MODELS:
            stmt = pg_insert(ModelConfig).values(**row).on_conflict_do_nothing(
                index_elements=["id"]
            )
            await session.execute(stmt)
        for row in SEED_PROMPTS:
            stmt = pg_insert(Prompt).values(**row).on_conflict_do_nothing(
                index_elements=["id"]
            )
            await session.execute(stmt)
        await session.commit()
        print(f"seeded {len(SEED_MODELS)} models, {len(SEED_PROMPTS)} prompts")


if __name__ == "__main__":
    asyncio.run(seed())
