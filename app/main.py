from __future__ import annotations

from flask import Flask, jsonify, request

from app.config import get_config
from app.logging_config import configure_logging
from app.trace import extract_trace_id
from app.webhook_handler import handle_update

app = Flask(__name__)

_config = get_config()
configure_logging(_config.log_level)


@app.get("/health")
def health() -> tuple[dict, int]:
    return {"status": "ok"}, 200


@app.post("/telegram/webhook")
def telegram_webhook() -> tuple[dict, int]:
    secret = request.headers.get("x-telegram-bot-api-secret-token", "")
    if secret != _config.webhook_secret:
        return {"error": "unauthorized"}, 401

    update = request.get_json(silent=True)
    if not update:
        return {"error": "invalid_json"}, 400

    try:
        trace_id = extract_trace_id(request.headers)
        result = handle_update(update, _config, trace_id=trace_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}, 500

    if result == "ignored":
        return {"status": "ignored"}, 200

    return {"status": "accepted"}, 200
