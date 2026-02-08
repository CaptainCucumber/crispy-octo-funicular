from __future__ import annotations

from flask import Flask, request

from app.config import get_config
from app.logging_config import configure_logging
from app.queue_worker import handle_pubsub_push

app = Flask(__name__)

_config = get_config()
configure_logging(_config.log_level)


@app.get("/health")
def health() -> tuple[dict, int]:
    return {"status": "ok"}, 200


@app.post("/pubsub/push")
def pubsub_push() -> tuple[dict, int]:
    payload = request.get_json(silent=True)
    if not payload:
        return {"error": "invalid_json"}, 400

    try:
        handle_pubsub_push(payload, request.headers, _config)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}, 500

    return {"status": "ok"}, 200
