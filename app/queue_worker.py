from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, Mapping

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import Config
from app.message_processor import process_update


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

    message = payload.get("message", {})
    data = message.get("data")
    if not data:
        raise ValueError("Missing Pub/Sub message data")

    decoded = base64.b64decode(data).decode("utf-8")
    update = json.loads(decoded)
    process_update(update, config)
