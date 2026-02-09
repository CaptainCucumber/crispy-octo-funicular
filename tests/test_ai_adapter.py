from datetime import datetime, timezone

from app.ai_adapter import generate_reply
from app.config import Config
from app.models import AIContext, Message, StyleProfile, User


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_generate_reply_builds_payload(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse({"choices": [{"message": {"content": "hello"}}]})

    monkeypatch.setattr("app.ai_adapter.requests.post", fake_post)

    config = Config(
        project_id="proj",
        ingest_chat_id=123,
        reply_chat_id=123,
        pubsub_topic="topic",
        pubsub_audience=None,
        telegram_token="token",
        openai_key="key",
        webhook_secret="secret",
        log_level="INFO",
        firestore_project_id=None,
        bot_username=None,
        bot_user_id=None,
    )

    context = AIContext(
        chat_id=123,
        recent_messages=[
            Message(
                message_id=1,
                sender=User(id=1, username="alice", first_name="Alice"),
                text="hello there",
                date=datetime.now(tz=timezone.utc),
                entities=[],
            )
        ],
        style_profile=StyleProfile(
            average_length=10,
            emoji_ratio=0,
            common_words=["hello"],
            topics=[],
        ),
    )

    reply = generate_reply(context, config)

    assert reply == "hello"
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer key"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][1]["content"] == "hello there"
