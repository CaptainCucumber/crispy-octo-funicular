from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from google.cloud import pubsub_v1

from app.config import Config
from app.trace import build_trace_context


logger = logging.getLogger(__name__)


def publish_update(update: Dict[str, Any], config: Config, trace_id: Optional[str] = None) -> str:
    client = pubsub_v1.PublisherClient()
    topic_path = client.topic_path(config.project_id, config.pubsub_topic)
    data = json.dumps(update).encode("utf-8")
    message_payload = update.get("message") or {}
    chat_id = (message_payload.get("chat") or {}).get("id")
    message_id = message_payload.get("message_id")
    update_id = update.get("update_id")
    trace_context = build_trace_context(trace_id, config.project_id)

    logger.info(
        "pubsub.message.publish",
        extra={
            "project_id": config.project_id,
            "topic": config.pubsub_topic,
            "update_id": update_id,
            "chat_id": chat_id,
            "message_id": message_id,
            **trace_context,
        },
    )
    attributes: Dict[str, str] = {}
    if trace_id:
        attributes["trace_id"] = trace_id
    future = client.publish(topic_path, data=data, **attributes)
    pubsub_message_id = future.result(timeout=10)
    logger.info(
        "pubsub.message.published",
        extra={
            "project_id": config.project_id,
            "topic": config.pubsub_topic,
            "update_id": update_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "pubsub_message_id": pubsub_message_id,
            **trace_context,
        },
    )
    return pubsub_message_id
