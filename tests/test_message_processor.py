from datetime import datetime, timedelta, timezone

from app.config import Config
from app.message_processor import process_update


def _config():
    return Config(
        project_id="proj",
        chat_id=123,
        pubsub_topic="topic",
        pubsub_audience=None,
        telegram_token="token",
        openai_key="key",
        webhook_secret="secret",
        log_level="INFO",
        firestore_project_id=None,
        bot_username="bot",
        bot_user_id=999,
    )


def test_process_update_sends_reply(monkeypatch):
    calls = {}

    monkeypatch.setattr("app.message_processor.is_update_processed", lambda *_: False)
    monkeypatch.setattr("app.message_processor.save_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.message_processor.get_last_reply_time",
        lambda *args, **kwargs: datetime.now(tz=timezone.utc) - timedelta(seconds=600),
    )
    monkeypatch.setattr(
        "app.message_processor.get_latest_messages",
        lambda *args, **kwargs: [
            {
                "message_id": 1,
                "text": "hello",
                "date": datetime.now(tz=timezone.utc).isoformat(),
                "user_id": 1,
                "username": "alice",
            }
        ],
    )
    monkeypatch.setattr("app.message_processor.generate_reply", lambda *_: "hi")
    monkeypatch.setattr(
        "app.message_processor._send_telegram_reply",
        lambda chat_id, text, config: calls.setdefault("sent", text),
    )
    monkeypatch.setattr(
        "app.message_processor.save_reply",
        lambda *args, **kwargs: calls.setdefault("reply_saved", True),
    )
    monkeypatch.setattr(
        "app.message_processor.mark_update_processed",
        lambda *args, **kwargs: calls.setdefault("marked", True),
    )
    monkeypatch.setattr("app.message_processor.random.random", lambda: 0.0)

    update = {
        "update_id": 10,
        "message": {
            "message_id": 55,
            "date": int(datetime.now(tz=timezone.utc).timestamp()),
            "text": "hello?",
            "from": {"id": 1, "username": "alice", "first_name": "Alice"},
        },
    }

    process_update(update, _config())

    assert calls.get("sent") == "hi"
    assert calls.get("reply_saved") is True
    assert calls.get("marked") is True


def test_process_update_skips_duplicates(monkeypatch):
    calls = {"saved": False}

    monkeypatch.setattr("app.message_processor.is_update_processed", lambda *_: True)

    def fake_save_message(*args, **kwargs):
        calls["saved"] = True

    monkeypatch.setattr("app.message_processor.save_message", fake_save_message)

    update = {
        "update_id": 11,
        "message": {
            "message_id": 56,
            "date": int(datetime.now(tz=timezone.utc).timestamp()),
            "text": "hello",
            "from": {"id": 2, "username": "bob", "first_name": "Bob"},
        },
    }

    process_update(update, _config())

    assert calls["saved"] is False
