"""Real HTTP contract tests against an immutable builtin engine snapshot."""

from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager

import pytest

from promptstyler_next import Engine
from promptstyler_next.service import MAX_BODY, create_server


@contextmanager
def running(engine=None):
    server = create_server(engine, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture(scope="module")
def server():
    with running() as value:
        yield value


def request(server, method="GET", path="/api/v1/health", body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        return response.status, dict(response.getheaders()), payload
    finally:
        connection.close()


def post(server, value, path="/api/v1/compose"):
    return request(server, "POST", path, json.dumps(value).encode(), {"Content-Type": "application/json"})


def test_loopback_binding_only():
    with pytest.raises(ValueError, match="loopback"):
        create_server(host="0.0.0.0", port=0)


def test_catalog_and_discovery_share_engine(server):
    engine = Engine.builtin()
    status, headers, raw = request(server, path="/api/v1/catalog")
    catalog = json.loads(raw)
    assert status == 200
    assert catalog["catalog_fingerprint"] == engine.catalog_fingerprint
    expected = []
    offset = 0
    while True:
        page = engine.list_styles(limit=1000, offset=offset)
        expected.extend(page)
        if len(page) < 1000:
            break
        offset += len(page)
    assert catalog["total"] == len(expected) == 1132
    status, _, raw = request(server, path="/api/v1/styles?limit=2&offset=1")
    assert status == 200
    assert json.loads(raw)["items"] == engine.list_styles(limit=2, offset=1)
    assert headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in headers


def test_real_engine_http_composition_parity(server):
    engine = Engine.builtin()
    style = engine.list_styles(limit=1)[0]
    recipe = {
        "prompt": 'A shop sign reading <Quiet> & "Books" 雨',
        "model": "flux",
        "styles": [{"id": style["id"], "intensity": 0.75}],
    }
    status, _, raw = post(server, recipe)
    assert status == 200
    assert json.loads(raw) == engine.compose(recipe).to_dict()


def test_profiles_and_detail(server):
    engine = Engine.builtin()
    status, _, raw = request(server, path="/api/v1/profiles")
    assert status == 200 and json.loads(raw)["items"] == engine.profiles()
    style = engine.list_styles(limit=1)[0]
    status, _, raw = request(server, path=f"/api/v1/styles/{style['id']}")
    assert status == 200 and json.loads(raw) == style
    assert request(server, path="/api/v1/styles/absent.style")[0] == 404


def test_recommendation_parity(server):
    body = {"prompt": "a cinematic portrait with soft lighting", "model": "sdxl", "limit": 3}
    status, _, raw = post(server, body, "/api/v1/recommend")
    assert status == 200
    assert json.loads(raw)["items"] == Engine.builtin().recommend(**body)


@pytest.mark.parametrize("path", ["/", "/styles.css", "/app.mjs", "/client.mjs"])
def test_assets_are_packaged_and_csp_is_local(server, path):
    status, headers, body = request(server, path=path)
    assert status == 200 and body
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize(
    "path",
    [
        "/../../AGENTS.md",
        "/%2e%2e/AGENTS.md",
        "/packs/core.json",
        "/api/v1/../profiles",
        "/api/v1/styles/id/other",
    ],
)
def test_no_arbitrary_file_or_route_access(server, path):
    assert request(server, path=path)[0] == 404


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "attacker.example"},
        {"Origin": "https://attacker.example"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_cross_site_and_rebinding_rejected(server, headers):
    status, _, raw = request(server, headers=headers)
    assert status == 403
    assert json.loads(raw)["error"]["code"].startswith("forbidden_")


def test_same_origin_accepted(server):
    origin = f"http://127.0.0.1:{server.server_port}"
    assert request(server, headers={"Origin": origin})[0] == 200


@pytest.mark.parametrize(
    "body",
    [
        b'{"prompt":"one","prompt":"two"}',
        b'{"prompt":"x","styles":[{"id":"x","intensity":NaN}]}',
        b"[]",
        b"null",
        b"{",
        b'"str"',
        b"\xff",
    ],
)
def test_json_rejections(server, body):
    status, _, raw = request(server, "POST", "/api/v1/compose", body, {"Content-Type": "application/json"})
    assert status == 400
    assert set(json.loads(raw)["error"]) == {"code", "message", "path"}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/styles?limit=bad",
        "/api/v1/styles?limit=-1",
        "/api/v1/styles?offset=999999",
        "/api/v1/styles?unknown=value",
        "/api/v1/styles?q=one&q=two",
        "/api/v1/profiles?x=1",
    ],
)
def test_invalid_query(server, path):
    assert request(server, path=path)[0] == 400


def test_request_body_and_media_limits(server):
    assert request(server, "POST", "/api/v1/compose", b"{}", {"Content-Type": "text/plain"})[0] == 415
    assert (
        request(
            server, "POST", "/api/v1/compose", b"x" * (MAX_BODY + 1), {"Content-Type": "application/json"}
        )[0]
        == 413
    )
    assert (
        request(
            server,
            "POST",
            "/api/v1/compose",
            b"{}",
            {"Content-Type": "application/json", "Transfer-Encoding": "chunked"},
        )[0]
        == 400
    )
    assert request(server, "OPTIONS")[0] == 405


def test_errors_do_not_echo_prompt(server):
    secret = "private-subject-never-log-this"
    status, _, raw = post(server, {"prompt": secret, "unexpected": secret})
    assert status == 400 and secret.encode() not in raw


def test_no_pack_upload_endpoint(server):
    assert post(server, {"path": "/tmp/test.json"}, "/api/v1/packs")[0] == 404


def test_concurrent_composition_is_reproducible(server):
    from concurrent.futures import ThreadPoolExecutor

    recipe = {"prompt": "A red book on a table", "model": "anima"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: post(server, recipe), range(8)))
    assert all(response[0] == 200 for response in responses)
    assert len({json.loads(response[2])["fingerprint"] for response in responses}) == 1


def test_workbench_filter_urls_survive_refresh(server):
    status, headers, raw = request(server, path="/?q=noir&model=flux&category=cinema&kind=style&favorites=1")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert b"PromptStyler Next" in raw
    assert request(server, path="/?unexpected=value")[0] == 400
    assert request(server, path="/app.mjs?unexpected=value")[0] == 400


@pytest.mark.parametrize("port", [-1, 65536, True])
def test_invalid_port_is_an_actionable_domain_error_before_binding(port):
    from promptstyler_next import StylerError

    with pytest.raises(StylerError) as error:
        create_server(port=port)
    assert error.value.code == "invalid_integer"
    assert error.value.path == "port"
