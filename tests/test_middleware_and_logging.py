from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import logging_config
from app.logging_config import scrub_event
from app.main import app


def test_chat_reuses_valid_request_id_and_logs_the_same_context(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            headers={"x-request-id": "req-abcdef12"},
            json={
                "user_id": "student-01",
                "session_id": "session-01",
                "feature": "qa",
                "message": "Explain observability",
            },
        )

    assert response.status_code == 200
    assert response.json()["correlation_id"] == "req-abcdef12"
    assert response.headers["x-request-id"] == "req-abcdef12"
    assert float(response.headers["x-response-time-ms"]) >= 0

    api_events = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if '"service": "api"' in line
    ]
    assert {event["correlation_id"] for event in api_events} == {"req-abcdef12"}
    assert all("user_id" not in event for event in api_events)


def test_pii_scrubber_handles_nested_payloads_and_error_text() -> None:
    event = scrub_event(
        None,
        "error",
        {
            "event": "request_failed",
            "payload": {
                "nested": {
                    "email": "student@vinuni.edu.vn",
                    "phone": "090 123 4567",
                },
                "error": "Card 4111 1111 1111 1111 was rejected",
            },
        },
    )
    rendered = json.dumps(event, ensure_ascii=False)

    assert "student@vinuni.edu.vn" not in rendered
    assert "090 123 4567" not in rendered
    assert "4111 1111 1111 1111" not in rendered
    assert len(re.findall(r"REDACTED_", rendered)) == 3
