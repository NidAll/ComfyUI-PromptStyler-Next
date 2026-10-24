"""Bounded, loopback-only HTTP transport for the shared styling engine."""

from __future__ import annotations

import argparse
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import Engine, StylerError
from .validation import integer, parse_json

_LOG = logging.getLogger(__name__)
MAX_BODY = 128 * 1024
MAX_QUERY = 4096
STATIC = {"/": "index.html", "/app.mjs": "app.mjs", "/styles.css": "styles.css", "/client.mjs": "client.mjs"}


def _error(code: str, message: str, path: str = "") -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "path": path}}


class StylerHTTPServer(ThreadingHTTPServer):
    """One immutable engine per server; no request or prompt history is retained."""

    daemon_threads = True
    request_queue_size = 16
    block_on_close = False

    def __init__(self, engine: Engine, host: str, port: int) -> None:
        self.engine = engine
        super().__init__((host, port), StylerHandler)


class StylerHandler(BaseHTTPRequestHandler):
    server: StylerHTTPServer
    server_version = "PromptStylerNext"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format: str, *args: object) -> None:
        # The default logger includes the request target, which can contain user text.
        _LOG.debug("HTTP %s", self.command)

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def _json(self, status: int, value: object) -> None:
        self._send(
            status,
            json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"),
        )

    def _guard(self) -> bool:
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        authority = self.headers.get("Host", "").lower()
        if len(self.headers.get_all("Host", [])) != 1 or authority not in allowed:
            self._json(403, _error("forbidden_host", "Use this service through its loopback address."))
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{authority}"}:
            self._json(
                403, _error("forbidden_origin", "Use the same-origin application or the HEISS server bridge.")
            )
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self._json(403, _error("forbidden_origin", "Cross-site requests are not accepted."))
            return False
        if len(self.path) > MAX_QUERY:
            self._json(414, _error("request_too_large", "The request URL is too long."))
            return False
        return True

    def _params(self, query: str, allowed: set[str]) -> dict[str, list[str]]:
        params = parse_qs(query, keep_blank_values=True, max_num_fields=32)
        if set(params) - allowed:
            raise ValueError("Unknown query parameter.")
        if any(len(values) != 1 for key, values in params.items() if key != "tag"):
            raise ValueError("Only tag may be repeated.")
        return params

    def do_GET(self) -> None:
        if not self._guard():
            return
        try:
            target = urlsplit(self.path)
        except ValueError:
            self._json(400, _error("invalid_request", "Use a valid request URL."))
            return
        path = unquote(target.path)
        engine = self.server.engine
        try:
            if path in STATIC:
                if path == "/":
                    self._params(target.query, {"q", "category", "kind", "model", "favorites"})
                elif target.query:
                    raise ValueError("Static assets do not accept query parameters.")
                resource = files("promptstyler_next").joinpath("web", STATIC[path])
                content_type = {".mjs": "text/javascript", ".html": "text/html", ".css": "text/css"}[
                    resource.name[resource.name.rfind(".") :]
                ]
                self._send(200, resource.read_bytes(), content_type + "; charset=utf-8")
            elif path == "/api/v1/health":
                self._params(target.query, set())
                self._json(
                    200,
                    {"status": "ok", "schema_version": 1, "catalog_fingerprint": engine.catalog_fingerprint},
                )
            elif path == "/api/v1/profiles":
                self._params(target.query, set())
                self._json(200, {"items": engine.profiles()})
            elif path == "/api/v1/styles":
                params = self._params(
                    target.query, {"q", "category", "model", "tag", "kind", "limit", "offset"}
                )

                def one(key: str, default: Any = None) -> Any:
                    return params.get(key, [default])[0]

                items = engine.list_styles(
                    query=one("q", ""),
                    category=one("category"),
                    model=one("model"),
                    tags=params.get("tag", []),
                    kind=one("kind"),
                    limit=int(one("limit", 100)),
                    offset=int(one("offset", 0)),
                )
                self._json(200, {"items": items, "catalog_fingerprint": engine.catalog_fingerprint})
            elif path.startswith("/api/v1/styles/") and "/" not in path[len("/api/v1/styles/") :]:
                self._params(target.query, set())
                self._json(200, engine.get_style(path[len("/api/v1/styles/") :]))
            elif path == "/api/v1/catalog":
                self._params(target.query, set())
                # Metadata is derived from the same public catalog as discovery.
                catalog_items: list[dict[str, Any]] = []
                offset = 0
                while True:
                    page = engine.list_styles(limit=100, offset=offset)
                    catalog_items.extend(page)
                    if len(page) < 100:
                        break
                    offset += len(page)
                self._json(
                    200,
                    {
                        "schema_version": 1,
                        "catalog_fingerprint": engine.catalog_fingerprint,
                        "total": len(catalog_items),
                        "categories": sorted({item["category"] for item in catalog_items}),
                        "kinds": sorted({item["kind"] for item in catalog_items}),
                    },
                )
            else:
                self._json(404, _error("not_found", "No endpoint exists at this path."))
        except StylerError as error:
            self._json(
                404 if error.code in {"unknown_style", "style_not_found"} else 400, {"error": error.to_dict()}
            )
        except (ValueError, UnicodeError):
            self._json(400, _error("invalid_request", "Check the query parameter names and values."))

    def do_POST(self) -> None:
        if not self._guard():
            return
        try:
            target = urlsplit(self.path)
        except ValueError:
            self._json(400, _error("invalid_request", "Use a valid request URL."))
            return
        if target.path not in {"/api/v1/compose", "/api/v1/recommend"} or target.query:
            self._json(404, _error("not_found", "No endpoint exists at this path."))
            return
        if self.headers.get("Transfer-Encoding"):
            self._json(400, _error("invalid_request", "Send JSON with Content-Length."))
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, _error("unsupported_media_type", "Send application/json."))
            return
        if len(self.headers.get_all("Content-Length", [])) != 1:
            self._json(411, _error("length_required", "Send exactly one Content-Length."))
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0:
            self._json(411, _error("length_required", "Send a valid Content-Length."))
            return
        if length > MAX_BODY:
            self._json(413, _error("request_too_large", "JSON requests must be at most 128 KiB."))
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete request.")
            body = parse_json(raw, max_bytes=MAX_BODY)
            if not isinstance(body, dict):
                raise ValueError("JSON object required.")
            if target.path == "/api/v1/compose":
                result = self.server.engine.compose(body).to_dict()
            else:
                if set(body) - {"prompt", "model", "limit"} or "prompt" not in body:
                    raise ValueError("Unexpected recommendation fields.")
                result = {"items": self.server.engine.recommend(**body)}
            self._json(200, result)
        except StylerError as error:
            self._json(400, {"error": error.to_dict()})
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self._json(400, _error("invalid_json", "Send a valid JSON object with the documented fields."))
        except (TimeoutError, ConnectionError):
            self.close_connection = True

    def do_OPTIONS(self) -> None:
        if self._guard():
            self._json(
                405, _error("method_not_allowed", "Use the same-origin application; CORS is not enabled.")
            )

    def do_HEAD(self) -> None:
        self.do_GET()


def create_server(
    engine: Engine | None = None, *, host: str = "127.0.0.1", port: int = 8791
) -> StylerHTTPServer:
    """Create an unstarted loopback server. ``port=0`` selects a test port."""
    if host not in {"127.0.0.1", "localhost"}:
        raise StylerError("invalid_host", "PromptStyler Next only binds to loopback (127.0.0.1).", "host")
    integer(port, "port", maximum=65535)
    return StylerHTTPServer(engine or Engine.builtin(), "127.0.0.1", port)


def serve(engine: Engine, *, host: str = "127.0.0.1", port: int = 8791) -> None:
    """Run the sidecar until interrupted, then release its listening socket."""
    with create_server(engine, host=host, port=port) as server:
        print(f"PromptStyler Next: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the local PromptStyler Next workbench and API.")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument(
        "--pack", action="append", default=[], help="Additional validated JSON style pack (repeatable)."
    )
    args = parser.parse_args(argv)
    engine = Engine.builtin()
    if args.pack:
        engine = engine.with_packs(args.pack)
    serve(engine, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
