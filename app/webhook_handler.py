from __future__ import annotations

from typing import Any, Dict

from app.config import Config
from app.queue_publisher import publish_update


def handle_update(update: Dict[str, Any], config: Config) -> str:
    message = update.get("message")
    if not message:
        return "ignored"

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id != config.ingest_chat_id:
        return "ignored"

    publish_update(update, config)
    return "published"
