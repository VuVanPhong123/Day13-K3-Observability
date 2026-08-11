from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

import yaml

from .metrics import percentile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
DEFAULT_LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_dashboard_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("dashboard"), dict):
        raise ValueError("dashboard config must contain a dashboard object")
    return payload


def load_log_records(
    path: Path = DEFAULT_LOG_PATH,
    *,
    window_minutes: int = 60,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = current - timedelta(minutes=window_minutes)
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        timestamp = _parse_timestamp(record.get("ts"))
        if timestamp is not None and timestamp >= cutoff:
            record["_parsed_ts"] = timestamp
            records.append(record)
    return records


def _panel_config(config: dict[str, Any], panel_id: str) -> dict[str, Any]:
    panels = config["dashboard"]["panels"]
    return next(panel for panel in panels if panel.get("id") == panel_id)


def _threshold_status(value: float, threshold: dict[str, Any]) -> str:
    operator = threshold.get("operator")
    target = float(threshold.get("value", 0))
    if operator == "lte":
        return "ok" if value <= target else "alert"
    if operator == "gte":
        return "ok" if value >= target else "alert"
    return "unknown"


def _bucket_counts(records: Iterable[dict[str, Any]]) -> Counter[str]:
    buckets: Counter[str] = Counter()
    for record in records:
        timestamp = record.get("_parsed_ts")
        if isinstance(timestamp, datetime):
            bucket = timestamp.replace(second=0, microsecond=0).isoformat()
            buckets[bucket] += 1
    return buckets


def build_dashboard_snapshot(
    *,
    log_path: Path = DEFAULT_LOG_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    config = load_dashboard_config(config_path)
    dashboard = config["dashboard"]
    window_minutes = int(dashboard["time_range_minutes"])
    records = load_log_records(log_path, window_minutes=window_minutes, now=now)
    response_records = [record for record in records if record.get("event") == "response_sent"]
    request_records = [record for record in records if record.get("event") == "request_received"]
    failed_records = [record for record in records if record.get("event") == "request_failed"]

    latencies = [
        int(record["latency_ms"])
        for record in response_records
        if isinstance(record.get("latency_ms"), (int, float))
    ]
    costs = [
        float(record["cost_usd"])
        for record in response_records
        if isinstance(record.get("cost_usd"), (int, float))
    ]
    input_tokens = [
        int(record["tokens_in"])
        for record in response_records
        if isinstance(record.get("tokens_in"), (int, float))
    ]
    output_tokens = [
        int(record["tokens_out"])
        for record in response_records
        if isinstance(record.get("tokens_out"), (int, float))
    ]
    quality_scores = [
        float(record["quality_score"])
        for record in response_records
        if isinstance(record.get("quality_score"), (int, float))
    ]

    request_buckets = _bucket_counts(request_records)
    cost_buckets: defaultdict[str, float] = defaultdict(float)
    for record in response_records:
        timestamp = record.get("_parsed_ts")
        cost = record.get("cost_usd")
        if isinstance(timestamp, datetime) and isinstance(cost, (int, float)):
            bucket = timestamp.replace(second=0, microsecond=0).isoformat()
            cost_buckets[bucket] += float(cost)

    error_breakdown = Counter(
        str(record.get("error_type", "unknown")) for record in failed_records
    )
    request_count = len(request_records)
    error_rate_pct = (len(failed_records) / request_count * 100) if request_count else 0.0
    request_rate = float(max(request_buckets.values(), default=0))
    total_cost = sum(costs)
    total_tokens = sum(input_tokens) + sum(output_tokens)
    quality_mean = mean(quality_scores) if quality_scores else 0.0

    latency_panel = _panel_config(config, "latency")
    traffic_panel = _panel_config(config, "traffic")
    errors_panel = _panel_config(config, "errors")
    cost_panel = _panel_config(config, "cost")
    tokens_panel = _panel_config(config, "tokens")
    quality_panel = _panel_config(config, "quality")

    panels = [
        {
            "id": "latency",
            "title": latency_panel["title"],
            "unit": latency_panel["unit"],
            "threshold": latency_panel["threshold"],
            "values": {
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
                "p99": percentile(latencies, 99),
            },
            "status": _threshold_status(
                percentile(latencies, 95), latency_panel["threshold"]
            ),
        },
        {
            "id": "traffic",
            "title": traffic_panel["title"],
            "unit": traffic_panel["unit"],
            "threshold": traffic_panel["threshold"],
            "values": {
                "request_count": request_count,
                "requests_per_minute": request_rate,
                "buckets": dict(sorted(request_buckets.items())),
            },
            "status": _threshold_status(request_rate, traffic_panel["threshold"]),
        },
        {
            "id": "errors",
            "title": errors_panel["title"],
            "unit": errors_panel["unit"],
            "threshold": errors_panel["threshold"],
            "values": {
                "error_rate_pct": round(error_rate_pct, 4),
                "failed_count": len(failed_records),
                "breakdown": dict(sorted(error_breakdown.items())),
            },
            "status": _threshold_status(error_rate_pct, errors_panel["threshold"]),
        },
        {
            "id": "cost",
            "title": cost_panel["title"],
            "unit": cost_panel["unit"],
            "threshold": cost_panel["threshold"],
            "values": {
                "total_usd": round(total_cost, 6),
                "by_minute": {
                    bucket: round(value, 6)
                    for bucket, value in sorted(cost_buckets.items())
                },
            },
            "status": _threshold_status(total_cost, cost_panel["threshold"]),
        },
        {
            "id": "tokens",
            "title": tokens_panel["title"],
            "unit": tokens_panel["unit"],
            "threshold": tokens_panel["threshold"],
            "values": {
                "input_total": sum(input_tokens),
                "output_total": sum(output_tokens),
                "total": total_tokens,
            },
            "status": _threshold_status(total_tokens, tokens_panel["threshold"]),
        },
        {
            "id": "quality",
            "title": quality_panel["title"],
            "unit": quality_panel["unit"],
            "threshold": quality_panel["threshold"],
            "values": {"mean": round(quality_mean, 4)},
            "status": _threshold_status(quality_mean, quality_panel["threshold"]),
        },
    ]

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "title": dashboard["title"],
        "source": str(Path(dashboard["panels"][0]["source"])),
        "time_range_minutes": window_minutes,
        "refresh_seconds": int(dashboard["refresh_seconds"]),
        "generated_at": current.isoformat(),
        "record_count": len(records),
        "panels": panels,
    }


def _display_values(panel: dict[str, Any]) -> str:
    values = panel["values"]
    panel_id = panel["id"]
    if panel_id == "latency":
        return " · ".join(f"{key.upper()} {value:.1f} ms" for key, value in values.items())
    if panel_id == "traffic":
        return f"{values['request_count']} requests · {values['requests_per_minute']:.1f} req/min"
    if panel_id == "errors":
        breakdown = ", ".join(
            f"{key}: {value}" for key, value in values["breakdown"].items()
        ) or "none"
        return f"{values['error_rate_pct']:.2f}% · {breakdown}"
    if panel_id == "cost":
        return f"${values['total_usd']:.6f} total"
    if panel_id == "tokens":
        return f"in {values['input_total']} · out {values['output_total']}"
    return f"mean {values['mean']:.3f}"


def render_dashboard_html(snapshot: dict[str, Any]) -> str:
    cards: list[str] = []
    for panel in snapshot["panels"]:
        threshold = panel["threshold"]
        threshold_text = (
            f"threshold: {threshold['aggregation']} {threshold['operator']} "
            f"{threshold['value']} {panel['unit']}"
        )
        cards.append(
            "<article class='panel'>"
            f"<div class='panel-heading'><h2>{html.escape(panel['title'])}</h2>"
            f"<span class='status {html.escape(panel['status'])}'>{html.escape(panel['status'])}</span></div>"
            f"<div class='value'>{html.escape(_display_values(panel))}</div>"
            f"<div class='meta'>unit: {html.escape(panel['unit'])} · {html.escape(threshold_text)}</div>"
            "</article>"
        )
    initial = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(snapshot['title'])}</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #0b1020; color: #ecf2ff; }}
    body {{ margin: 0; padding: 28px; background: radial-gradient(circle at top right, #172554, #0b1020 55%); }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    h2 {{ margin: 0; font-size: 16px; font-weight: 650; }}
    .subtle, .meta {{ color: #9fb0d0; font-size: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .panel {{ min-height: 142px; padding: 18px; border: 1px solid #263657; border-radius: 14px; background: rgba(17, 27, 54, .84); box-shadow: 0 12px 30px rgba(0,0,0,.16); }}
    .panel-heading {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .value {{ margin: 28px 0 18px; color: #f8fafc; font-size: 21px; font-variant-numeric: tabular-nums; }}
    .status {{ padding: 4px 8px; border-radius: 999px; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }}
    .status.ok {{ color: #bbf7d0; background: #14532d; }}
    .status.alert {{ color: #fecaca; background: #7f1d1d; }}
    .status.unknown {{ color: #fde68a; background: #78350f; }}
    code {{ color: #bfdbfe; }}
  </style>
</head>
<body>
  <header>
    <div><h1>{html.escape(snapshot['title'])}</h1>
      <div class="subtle">Source: <code>{html.escape(snapshot['source'])}</code> · default window: {snapshot['time_range_minutes']} minutes · refresh: {snapshot['refresh_seconds']} seconds</div>
    </div>
    <div class="subtle">records: <span id="record-count">{snapshot['record_count']}</span> · updated: <span id="updated-at">{html.escape(snapshot['generated_at'])}</span></div>
  </header>
  <main class="grid" id="panels">{''.join(cards)}</main>
  <script>
    const initialSnapshot = {initial};
    setInterval(() => window.location.reload(), {int(snapshot['refresh_seconds']) * 1000});
  </script>
</body>
</html>"""
