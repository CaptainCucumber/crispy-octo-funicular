from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, Mapping

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import Config
from app.message_processor import process_update


logger = logging.getLogger(__name__)


def _verify_pubsub_jwt(headers: Mapping[str, str], audience: str) -> None:
    auth_header = headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise ValueError("Missing Pub/Sub bearer token")

    token = auth_header.split(" ", 1)[1]
    request_adapter = google_requests.Request()
    id_token.verify_oauth2_token(token, request_adapter, audience=audience)


def handle_pubsub_push(payload: Dict[str, Any], headers: Mapping[str, str], config: Config) -> None:
    audience = config.pubsub_audience or ""
    skip_auth = os.getenv("SKIP_PUBSUB_AUTH", "false").lower() == "true"
    if not skip_auth:
        if not audience:
            raise ValueError("Missing Pub/Sub audience header")
        _verify_pubsub_jwt(headers, audience)
        logger.info("pubsub.auth.verified", extra={"audience": audience})
    else:
        logger.info("pubsub.auth.skipped")

    message = payload.get("message", {})
    pubsub_message_id = message.get("messageId")
    pubsub_publish_time = message.get("publishTime")
    data = message.get("data")
    if not data:
        logger.warning(
            "pubsub.message.missing_data",
            extra={
                "pubsub_message_id": pubsub_message_id,
                "pubsub_publish_time": pubsub_publish_time,
            },
        )
        raise ValueError("Missing Pub/Sub message data")

    decoded = base64.b64decode(data).decode("utf-8")
    update = json.loads(decoded)
    update_id = update.get("update_id")
    message_payload = update.get("message") or {}
    chat_id = (message_payload.get("chat") or {}).get("id")
    message_id = message_payload.get("message_id")

    logger.info(
        "pubsub.message.received",
        extra={
            "pubsub_message_id": pubsub_message_id,
            "pubsub_publish_time": pubsub_publish_time,
            "update_id": update_id,
            "chat_id": chat_id,
            "message_id": message_id,
        },
    )

    try:
        process_update(update, config)
        logger.info(
            "pubsub.message.processed",
            extra={
                "pubsub_message_id": pubsub_message_id,
                "update_id": update_id,
                "chat_id": chat_id,
                "message_id": message_id,
            },
        )
    except Exception:
        logger.exception(
            "pubsub.message.failed",
            extra={
                "pubsub_message_id": pubsub_message_id,
                "update_id": update_id,
                "chat_id": chat_id,
                "message_id": message_id,
            },
        )
        raise
