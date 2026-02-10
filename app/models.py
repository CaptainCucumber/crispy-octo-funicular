from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class User:
    id: int
    username: Optional[str]
    first_name: Optional[str]
    is_bot: bool = False


@dataclass
class MessageEntity:
    type: str
    offset: int
    length: int


@dataclass
class Message:
    message_id: int
    sender: User
    text: Optional[str]
    date: datetime
    entities: List[MessageEntity]


@dataclass
class Update:
    update_id: int
    message: Message


@dataclass
class StyleProfile:
    average_length: float
    emoji_ratio: float
    common_words: List[str]
    topics: List[str]


@dataclass
class AIContext:
    chat_id: int
    recent_messages: List[Message]
    style_profile: StyleProfile
    metadata: Optional[Dict[str, Any]] = None
