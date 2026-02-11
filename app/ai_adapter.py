from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests

from app.config import Config
from app.constants import (
    DEFAULT_MAX_REPLY_SENTENCES,
    DEFAULT_MODEL_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_OPENAI_BACKOFF_SECONDS,
    DEFAULT_OPENAI_MAX_RETRIES,
)
from app.models import AIContext


logger = logging.getLogger(__name__)


def _style_guidance(context: AIContext) -> str:
    profile = context.style_profile
    hints: List[str] = []

    if profile.common_words:
        hints.append(f"Common slang/words: {', '.join(profile.common_words)}")

    if profile.average_length <= 40:
        hints.append("Keep replies short and punchy.")
    elif profile.average_length >= 120:
        hints.append("Longer, more detailed replies are acceptable.")

    if profile.emoji_ratio >= 0.02:
        hints.append("Use emojis occasionally if it feels natural.")
    elif profile.emoji_ratio <= 0.005:
        hints.append("Avoid emojis unless the user uses them first.")

    if not hints:
        return ""
    return "Style notes: " + " ".join(hints)


def _build_messages(context: AIContext) -> List[Dict[str, str]]:
    style_hint = _style_guidance(context)
    system_prompt = (
        "You are a friendly participant in a Telegram group chat. "
        "Mimic the group tone and slang. "
        f"Keep replies to {DEFAULT_MAX_REPLY_SENTENCES} sentences or fewer. "
        "Do not mention being an AI or a bot."
    )
    if style_hint:
        system_prompt = f"{system_prompt} {style_hint}"
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    for msg in context.recent_messages:
        if not msg.text:
            continue
        messages.append({"role": "user", "content": msg.text})

    return messages


def _trim_reply(text: str, max_sentences: int) -> str:
    if max_sentences <= 0:
        return text.strip()
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(parts) <= max_sentences:
        return text.strip()
    return " ".join(parts[:max_sentences]).strip()


def generate_reply(context: AIContext, config: Config) -> str:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": _build_messages(context),
        "temperature": DEFAULT_MODEL_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
    }

    headers = {
        "Authorization": f"Bearer {config.openai_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_OPENAI_MAX_RETRIES + 1):
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=20,
            )
            if response.status_code == 429:
                raise requests.HTTPError("429 Too Many Requests", response=response)
            response.raise_for_status()
            data = response.json()
            reply = data["choices"][0]["message"]["content"].strip()
            return _trim_reply(reply, DEFAULT_MAX_REPLY_SENTENCES)
        except requests.HTTPError as exc:
            last_error = exc
            status = getattr(exc.response, "status_code", None)
            if status != 429:
                raise
        except requests.RequestException as exc:
            last_error = exc

        if attempt < DEFAULT_OPENAI_MAX_RETRIES:
            time.sleep(DEFAULT_OPENAI_BACKOFF_SECONDS * attempt)

    if last_error:
        logger.error("openai.request.failed", exc_info=last_error)
    return ""


def analyze_video_frames(
    frames: List[str], caption: Optional[str], config: Config
) -> str:
    """
    Analyze video frames using OpenAI Vision API to understand video content.
    
    Args:
        frames: List of base64-encoded frame images
        caption: Optional caption/text from the video post
        config: Application configuration
        
    Returns:
        Analysis summary of the video content
    """
    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
    
    # Build content with frames (limit to first 10 frames to avoid token limits)
    content: List[Dict[str, Any]] = []
    
    # Add text instruction
    instruction_text = (
        "Analyze these video frames extracted at 2-second intervals. "
        "Describe what's happening in the video, the main subjects, actions, "
        "setting, and overall theme. Be concise but comprehensive."
    )
    
    if caption:
        instruction_text += f"\n\nVideo caption: {caption}"
    
    content.append({"type": "text", "text": instruction_text})
    
    # Add frames (limit to avoid token overflow)
    max_frames = min(len(frames), 10)
    for i, frame_b64 in enumerate(frames[:max_frames]):
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{frame_b64}",
                "detail": "low",  # Use low detail to reduce tokens
            }
        })
    
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "max_tokens": 500,
        "temperature": 0.7,
    }
    
    headers = {
        "Authorization": f"Bearer {config.openai_key}",
        "Content-Type": "application/json",
    }
    
    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_OPENAI_MAX_RETRIES + 1):
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=60,  # Longer timeout for vision analysis
            )
            if response.status_code == 429:
                raise requests.HTTPError("429 Too Many Requests", response=response)
            response.raise_for_status()
            data = response.json()
            analysis = data["choices"][0]["message"]["content"].strip()
            logger.info(
                "video.analysis_complete",
                extra={"frames_analyzed": max_frames, "analysis_length": len(analysis)},
            )
            return analysis
        except requests.HTTPError as exc:
            last_error = exc
            status = getattr(exc.response, "status_code", None)
            if status != 429:
                raise
        except requests.RequestException as exc:
            last_error = exc
        
        if attempt < DEFAULT_OPENAI_MAX_RETRIES:
            time.sleep(DEFAULT_OPENAI_BACKOFF_SECONDS * attempt)
    
    if last_error:
        logger.error("video.analysis_failed", exc_info=last_error)
    return ""


def generate_video_comment(video_analysis: str, context: AIContext, config: Config) -> str:
    """
    Generate a comment about a video based on the video analysis.
    
    Args:
        video_analysis: Analysis summary of the video content
        context: AI context with recent messages and style profile
        config: Application configuration
        
    Returns:
        Generated comment text
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    style_hint = _style_guidance(context)
    system_prompt = (
        "You are commenting on an Instagram Reel video. "
        "Write an engaging, natural comment that responds to the video content. "
        f"Keep it brief ({DEFAULT_MAX_REPLY_SENTENCES} sentences or fewer). "
        "Be authentic and conversational, like a real person commenting."
    )
    if style_hint:
        system_prompt = f"{system_prompt} {style_hint}"
    
    user_message = f"Video content: {video_analysis}\n\nWrite a natural comment about this video."
    
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": DEFAULT_MODEL_TEMPERATURE,
        "max_tokens": 200,
    }
    
    headers = {
        "Authorization": f"Bearer {config.openai_key}",
        "Content-Type": "application/json",
    }
    
    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_OPENAI_MAX_RETRIES + 1):
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=20,
            )
            if response.status_code == 429:
                raise requests.HTTPError("429 Too Many Requests", response=response)
            response.raise_for_status()
            data = response.json()
            comment = data["choices"][0]["message"]["content"].strip()
            return _trim_reply(comment, DEFAULT_MAX_REPLY_SENTENCES)
        except requests.HTTPError as exc:
            last_error = exc
            status = getattr(exc.response, "status_code", None)
            if status != 429:
                raise
        except requests.RequestException as exc:
            last_error = exc
        
        if attempt < DEFAULT_OPENAI_MAX_RETRIES:
            time.sleep(DEFAULT_OPENAI_BACKOFF_SECONDS * attempt)
    
    if last_error:
        logger.error("video.comment_generation_failed", exc_info=last_error)
    return ""

