#!/usr/bin/env python3
"""Standard-library mock backend and HTTP assertions for the frontend image.

The harness has no production credentials or data.  Run ``serve`` inside a
throwaway Python container named ``backend`` and ``verify`` against the pure
frontend image on the same Docker network.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


RESPONSES = {
    "/api/v1/ping": (200, {"ok": True, "api": "v1"}),
    "/api/v2/company/CN/000725/profile": (
        200,
        {"ok": True, "symbol": "000725", "source": "controlled_fixture"},
    ),
    "/api/v2/company/CN/000725/history?period=annual": (
        200,
        {"ok": True, "symbol": "000725", "period": "annual"},
    ),
    "/api/v1/unauthorized": (401, {"detail": "fixture unauthorized"}),
    "/api/v1/forbidden": (403, {"detail": "fixture forbidden"}),
    "/api/v2/missing": (404, {"detail": "fixture missing"}),
    "/api/v2/invalid": (422, {"detail": "fixture invalid"}),
    "/api/v2/failure": (500, {"detail": "fixture failure"}),
    "/health": (200, {"status": "ok", "source": "mock_backend"}),
    "/health/missing": (404, {"detail": "fixture health missing"}),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        status, body = RESPONSES.get(
            self.path,
            (404, {"detail": "fixture backend route not found"}),
        )
        payload = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Request-ID", f"fixture-{status}")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def serve(port: int) -> None:
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


def fetch(base_url: str, path: str) -> tuple[int, str, bytes, str | None]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}")
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get_content_type(), exc.read(), exc.headers.get("X-Request-ID")
    with response:
        return response.status, response.headers.get_content_type(), response.read(), response.headers.get("X-Request-ID")


def verify(base_url: str) -> None:
    matrix = [
        ("/api/v1/ping", 200, "application/json"),
        ("/api/v2/company/CN/000725/profile", 200, "application/json"),
        ("/api/v2/company/CN/000725/history?period=annual", 200, "application/json"),
        ("/api/v1/unauthorized", 401, "application/json"),
        ("/api/v1/forbidden", 403, "application/json"),
        ("/api/v2/missing", 404, "application/json"),
        ("/api/v2/invalid", 422, "application/json"),
        ("/api/v2/failure", 500, "application/json"),
        ("/health", 200, "application/json"),
        ("/health/missing", 404, "application/json"),
        ("/stocks/CN/000725", 200, "text/html"),
    ]
    results = []
    for path, expected_status, expected_type in matrix:
        status, content_type, body, request_id = fetch(base_url, path)
        is_html = body.lstrip().lower().startswith(b"<!doctype html")
        assert status == expected_status, (path, status, expected_status)
        assert content_type == expected_type, (path, content_type, expected_type)
        if path.startswith("/api/") or path.startswith("/health"):
            assert not is_html, f"{path} returned SPA HTML"
            json.loads(body)
        else:
            assert is_html, f"{path} did not return SPA HTML"
        results.append(
            {
                "path": path,
                "status": status,
                "content_type": content_type,
                "request_id": request_id,
                "spa_html": is_html,
            }
        )
    print(json.dumps({"ok": True, "results": results}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--port", type=int, default=8000)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.port)
    else:
        verify(args.base_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
