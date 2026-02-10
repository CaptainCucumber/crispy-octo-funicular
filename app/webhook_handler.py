from __future__ import annotations

from typing import Any, Dict, Optional

from app.config import Config
from app.queue_publisher import publish_update


def handle_update(update: Dict[str, Any], config: Config, trace_id: Optional[str] = None) -> str:
    message = update.get("message")
    if not message:
        return "ignored"

    from_user = message.get("from") or {}
    if from_user.get("is_bot"):
        return "ignored"
    if config.bot_user_id and from_user.get("id") == config.bot_user_id:
        return "ignored"
    if not from_user:
        return "ignored"

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id != config.ingest_chat_id:
        return "ignored"

    publish_update(update, config, trace_id=trace_id)
    return "published"
