from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.dashboard import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_LOG_PATH,
    build_dashboard_snapshot,
    render_dashboard_html,
)


class DashboardHandler(BaseHTTPRequestHandler):
    config_path = DEFAULT_CONFIG_PATH
    log_path = DEFAULT_LOG_PATH

    def _snapshot(self) -> dict:
        return build_dashboard_snapshot(
            log_path=self.log_path,
            config_path=self.config_path,
        )

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path == "/api/dashboard":
            payload = json.dumps(self._snapshot(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path in {"/", "/index.html"}:
            payload = render_dashboard_html(self._snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Serve the Day 13 local dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print the current data-backed snapshot and exit.",
    )
    args = parser.parse_args()

    DashboardHandler.config_path = args.config
    DashboardHandler.log_path = args.log_path
    if args.once:
        snapshot = build_dashboard_snapshot(
            log_path=args.log_path,
            config_path=args.config,
        )
        print(json.dumps(snapshot, ensure_ascii=False))
        return 0

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard listening at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
