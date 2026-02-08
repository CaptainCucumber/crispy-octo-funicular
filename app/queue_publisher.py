from __future__ import annotations

import json
from typing import Any, Dict

from google.cloud import pubsub_v1

from app.config import Config


def publish_update(update: Dict[str, Any], config: Config) -> str:
    client = pubsub_v1.PublisherClient()
    topic_path = client.topic_path(config.project_id, config.pubsub_topic)
    data = json.dumps(update).encode("utf-8")
    future = client.publish(topic_path, data=data)
    return future.result(timeout=10)
