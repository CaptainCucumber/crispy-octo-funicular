from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from app.ai_adapter import analyze_video_frames, generate_reply, generate_video_comment
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
from app.trace import build_trace_context
from app.video_processor import VideoProcessor, encode_frame_to_base64

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


def _should_reply(update: Update, config: Config) -> bool:
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
        if delta.total_seconds() < DEFAULT_COOLDOWN_SECONDS:
            return False

    return random.random() < DEFAULT_REPLY_CHANCE


def _send_telegram_reply(chat_id: int, text: str, config: Config) -> None:
    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()


def process_update(update: Dict[str, Any], config: Config, trace_id: Optional[str] = None) -> None:
    parsed = _parse_update(update)
    message_payload = update.get("message") or {}
    chat_id = (message_payload.get("chat") or {}).get("id")
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
    
    # Check if this is a video message (Instagram Reel)
    video_info = message_payload.get("video") or message_payload.get("video_note")
    if video_info:
        _process_video_message(parsed, message_payload, config, log_context)
        mark_update_processed(parsed.update_id, config)
        logger.info("update.processed", extra=log_context)
        return

    should_reply = _should_reply(parsed, config)
    logger.info("reply.decision", extra={**log_context, "should_reply": should_reply})
    if not should_reply:
        mark_update_processed(parsed.update_id, config)
        logger.info("update.processed", extra=log_context)
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

    ai_context = AIContext(
        chat_id=config.ingest_chat_id,
        recent_messages=list(reversed(recent_messages)),
        style_profile=style_profile,
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


def _process_video_message(
    parsed: Update,
    message_payload: Dict[str, Any],
    config: Config,
    log_context: Dict[str, Any],
) -> None:
    """
    Process video messages (Instagram Reels) by extracting frames and analyzing content.
    
    Args:
        parsed: Parsed update object
        message_payload: Raw message payload
        config: Application configuration
        log_context: Logging context
    """
    logger.info("video.processing_started", extra=log_context)
    
    try:
        # Check if Instagram access token is configured
        if not hasattr(config, "instagram_access_token") or not config.instagram_access_token:
            logger.warning("video.no_instagram_token", extra=log_context)
            return
        
        # Get video file information
        video_info = message_payload.get("video") or message_payload.get("video_note")
        file_id = video_info.get("file_id")
        
        if not file_id:
            logger.error("video.no_file_id", extra=log_context)
            return
        
        # Download video file from Telegram
        video_url = _get_telegram_file_url(file_id, config)
        if not video_url:
            logger.error("video.url_retrieval_failed", extra=log_context)
            return
        
        # Process video: download and extract frames
        video_processor = VideoProcessor(config)
        frames = video_processor.process_video_url(video_url)
        
        if not frames:
            logger.error("video.no_frames_extracted", extra=log_context)
            return
        
        # Convert frames to base64 for AI analysis
        frames_b64 = [encode_frame_to_base64(frame) for frame in frames]
        
        # Get caption if available
        caption = message_payload.get("caption")
        
        # Analyze video content using AI
        video_analysis = analyze_video_frames(frames_b64, caption, config)
        
        if not video_analysis:
            logger.error("video.analysis_empty", extra=log_context)
            return
        
        logger.info("video.analysis_success", extra={**log_context, "analysis": video_analysis[:200]})
        
        # Generate comment based on video analysis
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
        
        ai_context = AIContext(
            chat_id=config.ingest_chat_id,
            recent_messages=list(reversed(recent_messages)),
            style_profile=style_profile,
        )
        
        comment = generate_video_comment(video_analysis, ai_context, config)
        
        if comment:
            _send_telegram_reply(config.reply_chat_id, comment, config)
            save_reply(config.reply_chat_id, parsed.message.message_id, comment, config)
            logger.info("video.comment_sent", extra={**log_context, "comment": comment})
        else:
            logger.warning("video.no_comment_generated", extra=log_context)
            
    except Exception:
        logger.exception("video.processing_failed", extra=log_context)


def _get_telegram_file_url(file_id: str, config: Config) -> Optional[str]:
    """
    Get the download URL for a Telegram file.
    
    Args:
        file_id: Telegram file ID
        config: Application configuration
        
    Returns:
        File download URL or None if retrieval fails
    """
    try:
        url = f"https://api.telegram.org/bot{config.telegram_token}/getFile"
        params = {"file_id": file_id}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if not data.get("ok"):
            logger.error("telegram.file_info_failed", extra={"file_id": file_id})
            return None
        
        file_path = data["result"].get("file_path")
        if not file_path:
            return None
        
        download_url = f"https://api.telegram.org/file/bot{config.telegram_token}/{file_path}"
        return download_url
        
    except Exception as e:
        logger.exception("telegram.file_url_error", extra={"error": str(e), "file_id": file_id})
        return None

