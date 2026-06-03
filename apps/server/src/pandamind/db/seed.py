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
        "id": "ollama-deepseek-r1-14b",
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
