from app.config import Config
from app.webhook_handler import handle_update


def test_handle_update_publishes(monkeypatch):
    calls = {}

    def fake_publish(update, config):
        calls["update"] = update

    monkeypatch.setattr("app.webhook_handler.publish_update", fake_publish)

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

    update = {
        "update_id": 1,
        "message": {
            "chat": {"id": 123},
            "text": "hi",
            "from": {"id": 10, "username": "alice", "is_bot": False},
        },
    }
    result = handle_update(update, config)

    assert calls["update"] == update
    assert result == "published"


def test_handle_update_rejects_other_chat(monkeypatch):
    monkeypatch.setattr("app.webhook_handler.publish_update", lambda *_: None)

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

    update = {
        "update_id": 1,
        "message": {
            "chat": {"id": 456},
            "text": "hi",
            "from": {"id": 10, "username": "alice", "is_bot": False},
        },
    }

    result = handle_update(update, config)
    assert result == "ignored"


def test_handle_update_ignores_missing_message(monkeypatch):
    monkeypatch.setattr("app.webhook_handler.publish_update", lambda *_: None)

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

    update = {"update_id": 1, "edited_message": {"text": "hi"}}
    result = handle_update(update, config)
    assert result == "ignored"
