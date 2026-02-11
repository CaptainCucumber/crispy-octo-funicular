from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from google.cloud import secretmanager


load_dotenv()


@dataclass(frozen=True)
class Config:
    project_id: str
    ingest_chat_id: int
    reply_chat_id: int
    pubsub_topic: str
    pubsub_audience: Optional[str]
    telegram_token: str
    openai_key: str
    webhook_secret: str
    log_level: str
    firestore_project_id: Optional[str]
    bot_username: Optional[str]
    bot_user_id: Optional[int]
    instagram_access_token: Optional[str]


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@lru_cache(maxsize=32)
def _access_secret(secret_resource: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    response = client.access_secret_version(name=secret_resource)
    return response.payload.data.decode("utf-8")


def _resolve_secret(env_value: str) -> str:
    if env_value.startswith("projects/"):
        return _access_secret(env_value)
    return env_value


@lru_cache(maxsize=1)
def get_config() -> Config:
    project_id = _require("PROJECT_ID")
    ingest_chat_id = int(_require("CHAT_ID"))
    reply_chat_id_value = os.getenv("REPLY_CHAT_ID")
    reply_chat_id = int(reply_chat_id_value) if reply_chat_id_value else ingest_chat_id
    pubsub_topic = _require("PUBSUB_TOPIC")
    pubsub_audience = os.getenv("PUBSUB_AUDIENCE")

    telegram_token = _resolve_secret(_require("TG_TOKEN"))
    openai_key = _resolve_secret(_require("OPENAI_KEY"))
    webhook_secret = _resolve_secret(_require("WEBHOOK_SECRET"))

    log_level = os.getenv("LOG_LEVEL", "INFO")
    firestore_project_id = os.getenv("FIRESTORE_PROJECT_ID")
    bot_username = os.getenv("BOT_USERNAME")
    bot_user_id = os.getenv("BOT_USER_ID")
    bot_user_id_value = int(bot_user_id) if bot_user_id else None
    
    # Instagram Basic Display API access token (optional)
    instagram_token_env = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    instagram_access_token = _resolve_secret(instagram_token_env) if instagram_token_env else None

    return Config(
        project_id=project_id,
        ingest_chat_id=ingest_chat_id,
        reply_chat_id=reply_chat_id,
        pubsub_topic=pubsub_topic,
        pubsub_audience=pubsub_audience,
        telegram_token=telegram_token,
        openai_key=openai_key,
        webhook_secret=webhook_secret,
        log_level=log_level,
        firestore_project_id=firestore_project_id,
        bot_username=bot_username,
        bot_user_id=bot_user_id_value,
        instagram_access_token=instagram_access_token,
    )
