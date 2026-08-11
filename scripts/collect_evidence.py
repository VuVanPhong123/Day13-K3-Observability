from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from app.cli import configure_utf8_stdio
from app.challenge import load_challenge
from app.dashboard import DEFAULT_CONFIG_PATH, DEFAULT_LOG_PATH, build_dashboard_snapshot
from app.metrics import percentile
from app.pii import scrub_value
from app.tracing import get_langfuse_client, tracing_enabled


EVIDENCE_DIR = REPO_ROOT / "submission" / "evidence"
TRACE_METADATA_FIELDS = {
    "user_id_hash",
    "session_id",
    "feature",
    "model",
    "env",
    "correlation_id",
    "prompt_name",
    "prompt_label",
    "prompt_version",
    "prompt_source",
    "doc_count",
    "prompt_fetch_error",
}


def _read_logs(path: Path = DEFAULT_LOG_PATH) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _safe_write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(scrub_value(payload), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _safe_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    return {
        key: scrub_value(value)
        for key, value in metadata.items()
        if key in TRACE_METADATA_FIELDS
    }


def _write_command_output(filename: str, command: list[str]) -> None:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed:\n{output}")
    (EVIDENCE_DIR / filename).write_text(scrub_value(output), encoding="utf-8")


def _trace_summary(trace: Any) -> dict[str, Any]:
    return {
        "trace_id": trace.id,
        "timestamp": trace.timestamp,
        "name": trace.name,
        "session_id": trace.session_id,
        "user_id": trace.user_id,
        "latency_seconds": trace.latency,
        "total_cost_usd": trace.total_cost,
        "metadata": _safe_metadata(trace.metadata),
        "tags": trace.tags,
        "html_path": trace.html_path,
    }


def _get_trace_with_backoff(client: Any, trace_id: str) -> Any:
    last_error: Exception | None = None
    for delay in (0, 5, 10):
        if delay:
            time.sleep(delay)
        try:
            return client.api.trace.get(trace_id)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not query Langfuse trace {trace_id}: {last_error}")


def _write_langfuse_evidence(log_records: list[dict[str, Any]], trace_id: str | None) -> None:
    if not tracing_enabled():
        raise RuntimeError("Langfuse tracing is disabled; cannot create real trace evidence")
    client = get_langfuse_client()
    listing = client.api.trace.list(
        name="agent_execution",
        limit=100,
        order_by="timestamp.desc",
        fields="core,io,observations",
    )
    logged_trace_ids = sorted(
        {
            record["trace_id"]
            for record in log_records
            if record.get("event") == "response_sent"
            and isinstance(record.get("trace_id"), str)
            and record["trace_id"]
        }
    )
    listed_ids = {trace.id for trace in listing.data}
    _safe_write_json(
        EVIDENCE_DIR / "langfuse-traces.json",
        {
            "query": {"name": "agent_execution", "limit": 100},
            "api_total_items": listing.meta.total_items,
            "logged_trace_id_count": len(logged_trace_ids),
            "logged_trace_ids": logged_trace_ids,
            "logged_ids_present_in_api_page": sorted(set(logged_trace_ids) & listed_ids),
            "traces": [_trace_summary(trace) for trace in listing.data],
        },
    )

    selected_id = trace_id
    if selected_id is None:
        response_records = [
            record
            for record in log_records
            if record.get("event") == "response_sent" and record.get("trace_id")
        ]
        if not response_records:
            raise RuntimeError("No response_sent log with a real trace_id was found")
        selected_id = str(
            max(response_records, key=lambda record: record.get("latency_ms", 0))["trace_id"]
        )

    trace = _get_trace_with_backoff(client, selected_id)
    waterfall = {
        **_trace_summary(trace),
        "observations": [
            {
                "id": observation.id,
                "name": observation.name,
                "type": observation.type,
                "latency_seconds": observation.latency,
                "parent_observation_id": observation.parent_observation_id,
                "prompt_name": observation.prompt_name,
                "prompt_version": observation.prompt_version,
                "metadata": _safe_metadata(observation.metadata),
            }
            for observation in trace.observations
        ],
    }
    _safe_write_json(EVIDENCE_DIR / "trace-waterfall.json", waterfall)


def _write_official_challenge_metrics(records: list[dict[str, Any]]) -> None:
    challenge = load_challenge(REPO_ROOT / "config" / "challenge.json")
    responses = sorted(
        (
            record
            for record in records
            if record.get("event") == "response_sent"
            and record.get("feature") == challenge.affected_feature
            and isinstance(record.get("latency_ms"), (int, float))
        ),
        key=lambda record: record.get("ts", ""),
    )
    selected = responses[-len(challenge.queries) :]
    if len(selected) != len(challenge.queries):
        raise RuntimeError("Could not find one response log for every official challenge query")
    latencies = [int(record["latency_ms"]) for record in selected]
    _safe_write_json(
        EVIDENCE_DIR / "challenge-request-metrics.json",
        {
            "challenge_id": challenge.challenge_id,
            "cohort": challenge.cohort,
            "affected_feature": challenge.affected_feature,
            "official_latency_threshold_ms": challenge.latency_threshold_ms,
            "selection": "latest response_sent records for the released official query count",
            "sample_size": len(selected),
            "latency_ms": {
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
                "p99": percentile(latencies, 99),
                "min": min(latencies),
                "max": max(latencies),
            },
            "correlation_ids": [record["correlation_id"] for record in selected],
            "trace_ids": [record.get("trace_id") for record in selected],
        },
    )


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Collect sanitized evidence from a real Day 13 runtime")
    parser.add_argument("--phase", choices=["baseline", "challenge"], required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--trace-id", help="Trace ID to use for the waterfall evidence")
    args = parser.parse_args()

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    records = _read_logs()
    if not records:
        raise RuntimeError("No runtime logs found; start the API and send requests first")

    snapshot = build_dashboard_snapshot(
        log_path=DEFAULT_LOG_PATH,
        config_path=DEFAULT_CONFIG_PATH,
    )
    _safe_write_json(EVIDENCE_DIR / f"{args.phase}-metrics.json", snapshot)
    _safe_write_json(EVIDENCE_DIR / "dashboard-runtime.json", snapshot)

    correlation_records = [
        record
        for record in records
        if record.get("correlation_id") == args.correlation_id
    ]
    if not correlation_records:
        raise RuntimeError(f"No logs found for correlation ID {args.correlation_id}")
    _safe_write_json(
        EVIDENCE_DIR / ("correlation-log.json" if args.phase == "baseline" else "challenge-log.json"),
        {
            "correlation_id": args.correlation_id,
            "records": correlation_records,
        },
    )

    pii_records = [
        record
        for record in records
        if "[REDACTED_" in json.dumps(record, ensure_ascii=False)
    ]
    if not pii_records:
        raise RuntimeError("No redacted runtime record was found for PII evidence")
    _safe_write_json(
        EVIDENCE_DIR / "pii-redaction-log.json",
        {"redacted_record_count": len(pii_records), "records": pii_records},
    )

    _write_command_output(
        "validate-logs.txt", [sys.executable, "scripts/validate_logs.py"]
    )
    _write_command_output(
        "validate-dashboard.txt", [sys.executable, "scripts/validate_dashboard.py"]
    )
    if args.phase == "challenge":
        _write_official_challenge_metrics(records)
    _write_langfuse_evidence(records, args.trace_id)

    print(f"Evidence collected for {args.phase}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
