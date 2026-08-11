from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from app.agent import LabAgent
from app.cli import configure_utf8_stdio
from app.pii import scrub_value
from app.tracing import flush, get_langfuse_client, tracing_enabled


PROMPT_NAME = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")
V1_TEMPLATE = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
V2_TEMPLATE = (
    "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}\n"
    "Answer concisely in a few sentences."
)
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


def _safe_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    return {
        key: scrub_value(value)
        for key, value in metadata.items()
        if key in TRACE_METADATA_FIELDS
    }


def _prompt_versions(client: Any) -> set[int]:
    response = client.api.prompts.list(name=PROMPT_NAME, limit=100)
    versions: set[int] = set()
    for item in response.data:
        if item.name == PROMPT_NAME:
            versions.update(int(version) for version in item.versions)
    return versions


def _ensure_prompt_versions(client: Any) -> dict[str, int]:
    versions = _prompt_versions(client)
    if 1 not in versions:
        created = client.create_prompt(
            name=PROMPT_NAME,
            prompt=V1_TEMPLATE,
            labels=["baseline", "production"],
            type="text",
            commit_message="Day 13 baseline prompt",
        )
        if int(created.version) != 1:
            raise RuntimeError(
                f"Expected first managed prompt version 1, got {created.version}"
            )
        versions.add(1)
    if 2 not in versions:
        created = client.create_prompt(
            name=PROMPT_NAME,
            prompt=V2_TEMPLATE,
            labels=["candidate"],
            type="text",
            commit_message="Day 13 candidate prompt",
        )
        if int(created.version) != 2:
            raise RuntimeError(
                f"Expected second managed prompt version 2, got {created.version}"
            )
        versions.add(2)

    baseline = client.api.prompts.get(PROMPT_NAME, version=1)
    candidate = client.api.prompts.get(PROMPT_NAME, version=2)
    if getattr(baseline, "prompt", None) != V1_TEMPLATE:
        raise RuntimeError("Managed version 1 does not satisfy the Day 13 prompt contract")
    if getattr(candidate, "prompt", None) != V2_TEMPLATE:
        raise RuntimeError("Managed version 2 does not satisfy the Day 13 prompt contract")

    # Remove production from v2 before assigning it to v1. This makes the
    # setup safe to rerun even if a previous run stopped during promotion.
    client.update_prompt(name=PROMPT_NAME, version=2, new_labels=["candidate"])
    client.update_prompt(
        name=PROMPT_NAME,
        version=1,
        new_labels=["baseline", "production"],
    )
    return {"baseline": 1, "candidate": 2}


def _trace_summary(client: Any, trace_id: str) -> dict[str, Any]:
    trace = client.api.trace.get(trace_id)
    observations = []
    for observation in trace.observations:
        observations.append(
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
        )
    return {
        "trace_id": trace.id,
        "name": trace.name,
        "session_id": trace.session_id,
        "user_id": trace.user_id,
        "metadata": _safe_metadata(trace.metadata),
        "observations": observations,
    }


def _wait_for_trace(client: Any, trace_id: str, timeout_seconds: int = 45) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    delay_seconds = 5
    while time.monotonic() < deadline:
        time.sleep(min(delay_seconds, max(0, deadline - time.monotonic())))
        try:
            return _trace_summary(client, trace_id)
        except Exception as exc:  # ingestion is eventually consistent
            last_error = exc
            retry_after = re.search(r"retryAfterSeconds': (\d+)", str(exc))
            delay_seconds = (
                int(retry_after.group(1))
                if retry_after
                else min(delay_seconds * 2, 15)
            )
    raise RuntimeError(f"Trace {trace_id} was not queryable after upload: {last_error}")


def _run_label(
    client: Any,
    agent: LabAgent,
    *,
    label: str,
    correlation_id: str,
    expected_version: int,
) -> dict[str, Any]:
    os.environ["LANGFUSE_PROMPT_LABEL"] = label
    result = agent.run(
        user_id="prompt-flow-user",
        feature="qa",
        session_id="prompt-flow-session",
        message="Explain how metrics, traces and logs work together.",
        correlation_id=correlation_id,
    )
    if not result.trace_id:
        raise RuntimeError("The managed prompt run did not produce a Langfuse trace ID")
    flush()
    summary = _wait_for_trace(client, result.trace_id)
    metadata = summary.get("metadata") or {}
    if metadata.get("prompt_source") != "langfuse":
        raise RuntimeError("Prompt flow used a local fallback instead of a managed prompt")
    if metadata.get("prompt_name") != PROMPT_NAME:
        raise RuntimeError("Trace prompt_name does not match the managed prompt")
    if metadata.get("prompt_label") != label:
        raise RuntimeError("Trace prompt_label does not match the requested label")
    if str(metadata.get("prompt_version")) != str(expected_version):
        raise RuntimeError("Trace prompt_version does not match the requested version")
    return {
        "label": label,
        "expected_version": expected_version,
        "trace_id": result.trace_id,
        "trace": summary,
    }


def main() -> int:
    configure_utf8_stdio()
    if not tracing_enabled():
        print("Langfuse tracing is disabled: both Langfuse keys are required in .env")
        return 1

    client = get_langfuse_client()
    versions = _ensure_prompt_versions(client)
    agent = LabAgent()
    evidence: dict[str, Any] = {
        "prompt_name": PROMPT_NAME,
        "versions": versions,
        "templates": {
            "baseline": V1_TEMPLATE,
            "candidate": V2_TEMPLATE,
        },
        "runs": [],
        "promotion": {},
        "rollback": {},
    }

    evidence["runs"].append(
        _run_label(
            client,
            agent,
            label="baseline",
            correlation_id="req-13030001",
            expected_version=versions["baseline"],
        )
    )
    evidence["runs"].append(
        _run_label(
            client,
            agent,
            label="candidate",
            correlation_id="req-13030002",
            expected_version=versions["candidate"],
        )
    )

    client.update_prompt(name=PROMPT_NAME, version=1, new_labels=["baseline"])
    client.update_prompt(
        name=PROMPT_NAME,
        version=2,
        new_labels=["candidate", "production"],
    )
    evidence["promotion"] = {
        "production_version": 2,
        "labels": {"baseline": ["baseline"], "candidate": ["candidate", "production"]},
    }
    evidence["runs"].append(
        _run_label(
            client,
            agent,
            label="production",
            correlation_id="req-13030003",
            expected_version=2,
        )
    )

    client.update_prompt(name=PROMPT_NAME, version=2, new_labels=["candidate"])
    client.update_prompt(
        name=PROMPT_NAME,
        version=1,
        new_labels=["baseline", "production"],
    )
    production = client.api.prompts.get(PROMPT_NAME, label="production")
    if int(production.version) != versions["baseline"]:
        raise RuntimeError("Production label did not roll back to version 1")
    evidence["rollback"] = {
        "production_version": int(production.version),
        "labels": {"baseline": ["baseline", "production"], "candidate": ["candidate"]},
    }
    evidence["runs"].append(
        _run_label(
            client,
            agent,
            label="production",
            correlation_id="req-13030004",
            expected_version=versions["baseline"],
        )
    )
    flush()

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "prompt-versions.json").write_text(
        json.dumps(scrub_value(evidence), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (EVIDENCE_DIR / "prompt-rollback.txt").write_text(
        "Managed prompt: "
        f"{PROMPT_NAME}\n"
        "Promotion: production -> version 2\n"
        "Rollback: production -> version 1\n"
        f"Final production version: {production.version}\n"
        "Trace IDs and metadata are recorded in prompt-versions.json.\n",
        encoding="utf-8",
    )

    print(f"Prompt: {PROMPT_NAME}")
    print("Versions: baseline=1, candidate=2")
    for run in evidence["runs"]:
        print(f"{run['label']}: v{run['expected_version']} | trace {run['trace_id']}")
    print(f"Final production version: {production.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
