from __future__ import annotations

import os
from typing import List, Dict, Any

import requests

from app.config import Config
from app.constants import DEFAULT_MODEL_TEMPERATURE, DEFAULT_MAX_TOKENS
from app.models import AIContext


def _build_messages(context: AIContext) -> List[Dict[str, str]]:
    system_prompt = (
        "You are a friendly participant in a Telegram group chat. "
        "Mimic the group tone and slang. Keep replies concise. "
        "Do not mention being an AI or a bot."
    )
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    for msg in context.recent_messages:
        if not msg.text:
            continue
        messages.append({"role": "user", "content": msg.text})

    return messages


def generate_reply(context: AIContext, config: Config) -> str:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": _build_messages(context),
        "temperature": DEFAULT_MODEL_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
    }

    headers = {
        "Authorization": f"Bearer {config.openai_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        json=payload,
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()
