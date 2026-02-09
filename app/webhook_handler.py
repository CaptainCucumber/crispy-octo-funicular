from __future__ import annotations

from typing import Any, Dict

from app.config import Config
from app.queue_publisher import publish_update


def handle_update(update: Dict[str, Any], config: Config) -> None:
    message = update.get("message")
    if not message:
        raise ValueError("Unsupported update type")

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id != config.ingest_chat_id:
        raise ValueError("Chat ID not allowed")

    publish_update(update, config)
