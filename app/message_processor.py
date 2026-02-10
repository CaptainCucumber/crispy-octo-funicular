from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

from app.ai_adapter import generate_reply
from app.config import Config
from app.constants import (
    DEFAULT_CONTEXT_MESSAGES,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_REPLY_CHANCE,
)
from app.models import AIContext, Message, MessageEntity, StyleProfile, Update, User
from app.storage import (
    get_last_reply_time,
    get_latest_messages,
    is_update_processed,
    mark_update_processed,
    save_message,
    save_reply,
)

logger = logging.getLogger(__name__)


def _parse_update(update: Dict[str, Any]) -> Update:
    message = update["message"]
    from_user = message.get("from", {})
    user = User(
        id=from_user.get("id"),
        username=from_user.get("username"),
        first_name=from_user.get("first_name"),
    )

    entities = [
        MessageEntity(type=e.get("type"), offset=e.get("offset"), length=e.get("length"))
        for e in message.get("entities", [])
    ]

    date_value = datetime.fromtimestamp(message.get("date"), tz=timezone.utc)
    msg = Message(
        message_id=message.get("message_id"),
        sender=user,
        text=message.get("text"),
        date=date_value,
        entities=entities,
    )

    return Update(update_id=update["update_id"], message=msg)


def _build_style_profile(messages: List[Dict[str, Any]]) -> StyleProfile:
    texts = [m.get("text", "") for m in messages if m.get("text")]
    if not texts:
        return StyleProfile(average_length=0, emoji_ratio=0, common_words=[], topics=[])

    total_length = sum(len(t) for t in texts)
    average_length = total_length / len(texts)
    emoji_count = sum(len(re.findall(r"[\U0001F300-\U0001FAFF]", t)) for t in texts)
    emoji_ratio = emoji_count / max(total_length, 1)

    words = re.findall(r"\b\w+\b", " ".join(texts).lower())
    common_words = [w for w in sorted(set(words), key=words.count, reverse=True)[:5]]

    topics = []
    return StyleProfile(
        average_length=average_length,
        emoji_ratio=emoji_ratio,
        common_words=common_words,
        topics=topics,
    )


def _should_reply(update: Update, config: Config) -> bool:
    if config.bot_user_id and update.message.sender.id == config.bot_user_id:
        return False

    text = update.message.text or ""
    if config.bot_username and f"@{config.bot_username}" in text:
        return True

    if "?" in text:
        return True

    last_reply_time = get_last_reply_time(config.reply_chat_id, config)
    if last_reply_time:
        delta = datetime.now(tz=timezone.utc) - last_reply_time
        if delta.total_seconds() < DEFAULT_COOLDOWN_SECONDS:
            return False

    return random.random() < DEFAULT_REPLY_CHANCE


def _send_telegram_reply(chat_id: int, text: str, config: Config) -> None:
    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()


def process_update(update: Dict[str, Any], config: Config) -> None:
    parsed = _parse_update(update)
    message_payload = update.get("message") or {}
    chat_id = (message_payload.get("chat") or {}).get("id")
    context = {
        "update_id": parsed.update_id,
        "chat_id": chat_id,
        "message_id": parsed.message.message_id,
        "user_id": parsed.message.sender.id,
        "username": parsed.message.sender.username,
    }
    if is_update_processed(parsed.update_id, config):
        logger.info("update.duplicate", extra=context)
        return

    save_message(
        chat_id=config.ingest_chat_id,
        message_id=parsed.message.message_id,
        payload={
            "message_id": parsed.message.message_id,
            "text": parsed.message.text,
            "date": parsed.message.date.isoformat(),
            "user_id": parsed.message.sender.id,
            "username": parsed.message.sender.username,
        },
        config=config,
    )
    logger.info("message.saved", extra=context)

    should_reply = _should_reply(parsed, config)
    logger.info("reply.decision", extra={**context, "should_reply": should_reply})
    if not should_reply:
        mark_update_processed(parsed.update_id, config)
        logger.info("update.processed", extra=context)
        return

    history = get_latest_messages(config.ingest_chat_id, DEFAULT_HISTORY_LIMIT, config)
    style_profile = _build_style_profile(history)

    recent_messages = [
        Message(
            message_id=m.get("message_id"),
            sender=User(
                id=m.get("user_id"),
                username=m.get("username"),
                first_name=None,
            ),
            text=m.get("text"),
            date=datetime.fromisoformat(m.get("date")),
            entities=[],
        )
        for m in history[:DEFAULT_CONTEXT_MESSAGES]
    ]

    context = AIContext(
        chat_id=config.ingest_chat_id,
        recent_messages=list(reversed(recent_messages)),
        style_profile=style_profile,
    )

    reply = generate_reply(context, config)
    if reply:
        _send_telegram_reply(config.reply_chat_id, reply, config)
        save_reply(config.reply_chat_id, parsed.message.message_id, reply, config)
        logger.info("reply.sent", extra={**context, "reply_chat_id": config.reply_chat_id})
    else:
        logger.info("reply.empty", extra=context)

    mark_update_processed(parsed.update_id, config)
    logger.info("update.processed", extra=context)
