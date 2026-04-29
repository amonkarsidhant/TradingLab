"""
Dashboard Server — lightweight HTTP server for the trading lab dashboard.

Runs on localhost:8080. Auto-regenerates the dashboard HTML every 5 minutes.
Serves the latest dashboard, favicon, and static assets.

Usage:
    python scripts/dashboard_server.py

Or as a daemon via LaunchAgent.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Add src to path so imports work when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_lab.config import get_settings
from trading_lab.reports.dashboard import DashboardGenerator


DASHBOARD_PATH = Path(__file__).resolve().parents[1] / "docs" / "dashboard.html"
REFRESH_INTERVAL_SEC = 300  # regenerate every 5 minutes
PORT = 8080


def _generate_dashboard() -> str:
    """Generate the latest dashboard HTML."""
    settings = get_settings()
    generator = DashboardGenerator(
        db_path=settings.db_path,
        cache_db_path=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    html = generator.generate(ticker="SPY", data_source="yfinance")
    # Inject auto-refresh meta tag
    refresh_tag = f'<meta http-equiv="refresh" content="{REFRESH_INTERVAL_SEC}">'
    html = html.replace("</head>", f"{refresh_tag}\n</head>")
    return html


def _write_dashboard(html: str) -> None:
    """Write dashboard HTML to disk."""
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(html, encoding="utf-8")


def _regenerator() -> None:
    """Background thread that regenerates the dashboard periodically."""
    while True:
        try:
            html = _generate_dashboard()
            _write_dashboard(html)
            print(f"[{datetime.now(timezone.utc).isoformat()}] Dashboard regenerated")
        except Exception as exc:
            print(f"[{datetime.now(timezone.utc).isoformat()}] Dashboard regeneration failed: {exc}")
        time.sleep(REFRESH_INTERVAL_SEC)


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve the dashboard HTML and minimal API endpoints."""

    def log_message(self, format, *args):
        # Reduce noise — only log errors
        if "404" in args[0] or "500" in args[0]:
            super().log_message(format, *args)

    def do_GET(self) -> None:
        path = self.path

        if path in ("/", "/index.html", "/dashboard"):
            self._serve_dashboard()
            return

        if path == "/api/status":
            self._serve_json({
                "status": "ok",
                "generated_at": DASHBOARD_PATH.stat().st_mtime if DASHBOARD_PATH.exists() else None,
                "refresh_interval_sec": REFRESH_INTERVAL_SEC,
            })
            return

        if path == "/api/refresh":
            # Manual refresh endpoint
            try:
                html = _generate_dashboard()
                _write_dashboard(html)
                self._serve_json({"status": "refreshed", "path": str(DASHBOARD_PATH)})
            except Exception as exc:
                self._serve_json({"status": "error", "message": str(exc)}, code=500)
            return

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        self.send_error(404)

    def _serve_dashboard(self) -> None:
        if not DASHBOARD_PATH.exists():
            self.send_error(503, "Dashboard not generated yet")
            return

        html = DASHBOARD_PATH.read_text(encoding="utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_json(self, data: dict, code: int = 200) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    # Ensure initial dashboard exists
    print("Generating initial dashboard...")
    try:
        html = _generate_dashboard()
        _write_dashboard(html)
        print(f"Dashboard written to {DASHBOARD_PATH}")
    except Exception as exc:
        print(f"WARNING: Initial generation failed: {exc}")

    # Start background regenerator
    threading.Thread(target=_regenerator, daemon=True).start()

    # Start HTTP server
    server = HTTPServer(("localhost", PORT), DashboardHandler)
    url = f"http://localhost:{PORT}"
    print(f"Dashboard server running at {url}")
    print(f"Auto-regenerates every {REFRESH_INTERVAL_SEC // 60} minutes")
    print("Press Ctrl+C to stop")

    # Auto-open browser on macOS
    if sys.platform == "darwin":
        os.system(f"open {url}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
