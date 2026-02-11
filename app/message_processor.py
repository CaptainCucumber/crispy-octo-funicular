from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from app.ai_adapter import generate_reply
from app.config import Config
from app.constants import (
    DEFAULT_CONTEXT_MESSAGES,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_REPLY_CHANCE,
    DEFAULT_MAX_REPLY_SENTENCES,
    DEFAULT_MODEL_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_SYSTEM_PROMPT,
)
from app.models import AIContext, Message, MessageEntity, StyleProfile, Update, User
from app.storage import (
    get_last_reply_time,
    get_latest_messages,
    get_runtime_config,
    is_update_processed,
    save_runtime_config,
    clear_runtime_config,
    mark_update_processed,
    save_message,
    save_reply,
)
from app.trace import build_trace_context

logger = logging.getLogger(__name__)


def _parse_update(update: Dict[str, Any]) -> Update:
    message = update["message"]
    from_user = message.get("from", {})
    user = User(
        id=from_user.get("id"),
        username=from_user.get("username"),
        first_name=from_user.get("first_name"),
        is_bot=bool(from_user.get("is_bot", False)),
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


def _should_reply(
    update: Update,
    config: Config,
    reply_chance: float,
    cooldown_seconds: int,
) -> bool:
    if update.message.sender.is_bot:
        return False

    if update.message.sender.id is None:
        return False

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
        if delta.total_seconds() < cooldown_seconds:
            return False

    return random.random() < reply_chance


def _extract_command(text: str, bot_username: Optional[str]) -> Optional[tuple[str, str]]:
    if not text or not text.startswith("/"):
        return None

    first, *rest = text.strip().split(maxsplit=1)
    command_part = first[1:]
    if not command_part:
        return None

    if "@" in command_part:
        command, username = command_part.split("@", 1)
        if bot_username and username.lower() != bot_username.lower():
            return None
    else:
        command = command_part

    args = rest[0] if rest else ""
    return command.lower(), args


def _parse_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_admin_dm(message_payload: Dict[str, Any], config: Config, sender_id: Optional[int]) -> bool:
    if not config.admin_user_id:
        return False
    if sender_id is None or sender_id != config.admin_user_id:
        return False
    chat = message_payload.get("chat") or {}
    return chat.get("type") == "private"


def _handle_admin_command(
    update: Update,
    message_payload: Dict[str, Any],
    config: Config,
    runtime_config: Dict[str, Any],
) -> bool:
    text = update.message.text or ""
    parsed = _extract_command(text, config.bot_username)
    if not parsed:
        return False

    command, args = parsed
    args = args.strip()

    def reply(text_out: str) -> None:
        chat_id = (message_payload.get("chat") or {}).get("id")
        if chat_id:
            logger.info("admin.reply.sending", extra={"chat_id": chat_id, "text_length": len(text_out)})
            _send_telegram_reply(chat_id, text_out, config)
        else:
            logger.warning("admin.reply.no_chat_id")

    if command in {"help", "commands"}:
        reply(
            "Commands: /get_config, /reset_config, /set_reply_chance <0-1>, "
            "/set_cooldown <seconds>, /set_context_messages <int>, /set_history_limit <int>, "
            "/set_max_reply_sentences <int>, /set_model_temperature <0-2>, /set_max_tokens <int>, "
            "/set_system_prompt <text>"
        )
        return True

    if command == "get_config":
        effective = {
            "reply_chance": runtime_config.get("reply_chance", DEFAULT_REPLY_CHANCE),
            "cooldown_seconds": runtime_config.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS),
            "context_messages": runtime_config.get("context_messages", DEFAULT_CONTEXT_MESSAGES),
            "history_limit": runtime_config.get("history_limit", DEFAULT_HISTORY_LIMIT),
            "max_reply_sentences": runtime_config.get(
                "max_reply_sentences", DEFAULT_MAX_REPLY_SENTENCES
            ),
            "model_temperature": runtime_config.get(
                "model_temperature", DEFAULT_MODEL_TEMPERATURE
            ),
            "max_tokens": runtime_config.get("max_tokens", DEFAULT_MAX_TOKENS),
            "system_prompt": runtime_config.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
        }
        reply(
            "Current config:\n"
            + "\n".join(f"{key}={value}" for key, value in effective.items())
        )
        return True

    if command == "reset_config":
        clear_runtime_config(config)
        reply("Runtime config cleared.")
        return True

    updates: Dict[str, Any] = {}
    if command == "set_reply_chance":
        value = _parse_float(args)
        if value is None or not 0 <= value <= 1:
            reply("Invalid reply_chance. Expected a number between 0 and 1.")
            return True
        updates["reply_chance"] = value
    elif command == "set_cooldown":
        value = _parse_int(args)
        if value is None or value < 0:
            reply("Invalid cooldown. Expected a non-negative integer.")
            return True
        updates["cooldown_seconds"] = value
    elif command == "set_context_messages":
        value = _parse_int(args)
        if value is None or value <= 0:
            reply("Invalid context_messages. Expected a positive integer.")
            return True
        updates["context_messages"] = value
    elif command == "set_history_limit":
        value = _parse_int(args)
        if value is None or value <= 0:
            reply("Invalid history_limit. Expected a positive integer.")
            return True
        updates["history_limit"] = value
    elif command == "set_max_reply_sentences":
        value = _parse_int(args)
        if value is None or value < 0:
            reply("Invalid max_reply_sentences. Expected 0 or a positive integer.")
            return True
        updates["max_reply_sentences"] = value
    elif command == "set_model_temperature":
        value = _parse_float(args)
        if value is None or not 0 <= value <= 2:
            reply("Invalid model_temperature. Expected a number between 0 and 2.")
            return True
        updates["model_temperature"] = value
    elif command == "set_max_tokens":
        value = _parse_int(args)
        if value is None or value <= 0:
            reply("Invalid max_tokens. Expected a positive integer.")
            return True
        updates["max_tokens"] = value
    elif command == "set_system_prompt":
        if not args:
            reply("Invalid system_prompt. Provide the prompt text after the command.")
            return True
        updates["system_prompt"] = args
    else:
        reply("Unknown command. Use /help for a list of commands.")
        return True

    runtime_config.update(updates)
    save_runtime_config(config, runtime_config)
    reply("Updated runtime config.")
    return True


def _send_telegram_reply(chat_id: int, text: str, config: Config) -> None:
    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()


def process_update(update: Dict[str, Any], config: Config, trace_id: Optional[str] = None) -> None:
    parsed = _parse_update(update)
    message_payload = update.get("message") or {}
    chat_id = (message_payload.get("chat") or {}).get("id")
    runtime_config = get_runtime_config(config)
    trace_context = build_trace_context(trace_id, config.project_id)
    log_context = {
        "update_id": parsed.update_id,
        "chat_id": chat_id,
        "message_id": parsed.message.message_id,
        "user_id": parsed.message.sender.id,
        "username": parsed.message.sender.username,
        **trace_context,
    }
    if is_update_processed(parsed.update_id, config):
        logger.info("update.duplicate", extra=log_context)
        return

    if _is_admin_dm(message_payload, config, parsed.message.sender.id):
        try:
            handled = _handle_admin_command(parsed, message_payload, config, runtime_config)
            mark_update_processed(parsed.update_id, config)
            logger.info("admin.command", extra={**log_context, "handled": handled})
        except Exception:
            logger.exception("admin.command.failed", extra=log_context)
            mark_update_processed(parsed.update_id, config)
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
    logger.info("message.saved", extra=log_context)

    history_limit = int(runtime_config.get("history_limit", DEFAULT_HISTORY_LIMIT))
    context_messages = int(runtime_config.get("context_messages", DEFAULT_CONTEXT_MESSAGES))
    reply_chance = float(runtime_config.get("reply_chance", DEFAULT_REPLY_CHANCE))
    cooldown_seconds = int(
        runtime_config.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS)
    )

    should_reply = _should_reply(parsed, config, reply_chance, cooldown_seconds)
    logger.info("reply.decision", extra={**log_context, "should_reply": should_reply})
    if not should_reply:
        mark_update_processed(parsed.update_id, config)
        logger.info("update.processed", extra=log_context)
        return

    history = get_latest_messages(config.ingest_chat_id, history_limit, config)
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
        for m in history[:context_messages]
    ]

    ai_context = AIContext(
        chat_id=config.ingest_chat_id,
        recent_messages=list(reversed(recent_messages)),
        style_profile=style_profile,
        metadata={
            "max_reply_sentences": runtime_config.get(
                "max_reply_sentences", DEFAULT_MAX_REPLY_SENTENCES
            ),
            "model_temperature": runtime_config.get(
                "model_temperature", DEFAULT_MODEL_TEMPERATURE
            ),
            "max_tokens": runtime_config.get("max_tokens", DEFAULT_MAX_TOKENS),
            "system_prompt": runtime_config.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
        },
    )

    try:
        reply = generate_reply(ai_context, config)
        if reply:
            _send_telegram_reply(config.reply_chat_id, reply, config)
            save_reply(config.reply_chat_id, parsed.message.message_id, reply, config)
            logger.info(
                "reply.sent",
                extra={**log_context, "reply_chat_id": config.reply_chat_id},
            )
        else:
            logger.info("reply.empty", extra=log_context)
    except Exception:
        logger.exception("reply.failed", extra=log_context)
    finally:
        mark_update_processed(parsed.update_id, config)
        logger.info("update.processed", extra=log_context)
