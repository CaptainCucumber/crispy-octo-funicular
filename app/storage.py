from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from google.cloud import firestore

from app.config import Config


_client_cache: Dict[str, firestore.Client] = {}


def _get_client(config: Config) -> firestore.Client:
    project_id = config.firestore_project_id or config.project_id
    if project_id not in _client_cache:
        _client_cache[project_id] = firestore.Client(project=project_id)
    return _client_cache[project_id]


def is_update_processed(update_id: int, config: Config) -> bool:
    client = _get_client(config)
    doc = client.collection("processed_updates").document(str(update_id)).get()
    return doc.exists


def mark_update_processed(update_id: int, config: Config) -> None:
    client = _get_client(config)
    client.collection("processed_updates").document(str(update_id)).set(
        {"processed_at": datetime.now(tz=timezone.utc).isoformat()}
    )


def save_message(chat_id: int, message_id: int, payload: Dict[str, Any], config: Config) -> None:
    client = _get_client(config)
    client.collection("chats").document(str(chat_id)).collection("messages").document(
        str(message_id)
    ).set(payload)


def get_latest_messages(chat_id: int, limit: int, config: Config) -> list[Dict[str, Any]]:
    client = _get_client(config)
    docs = (
        client.collection("chats")
        .document(str(chat_id))
        .collection("messages")
        .order_by("date", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def save_reply(chat_id: int, message_id: int, reply_text: str, config: Config) -> None:
    client = _get_client(config)
    client.collection("chats").document(str(chat_id)).collection("replies").document(
        str(message_id)
    ).set({"reply_text": reply_text, "date": datetime.now(tz=timezone.utc).isoformat()})


def get_last_reply_time(chat_id: int, config: Config) -> Optional[datetime]:
    client = _get_client(config)
    docs = (
        client.collection("chats")
        .document(str(chat_id))
        .collection("replies")
        .order_by("date", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )
    for doc in docs:
        data = doc.to_dict() or {}
        value = data.get("date")
        if value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
    return None
