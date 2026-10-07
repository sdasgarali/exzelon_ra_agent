"""Hosted mode: real Streamable HTTP server, per-request bearer keys, host checks."""
from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
from conftest import result_json
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from neuraleads_mcp.__main__ import build_http_app
from neuraleads_mcp.config import Settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def hosted(backend):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # A server-wide key is configured on purpose: hosted mode must never use it.
    settings = Settings(api_url=backend["api_url"], api_key=backend["B"]["keys"]["admin"],
                        http_host="127.0.0.1", http_port=port, max_retries=0)
    server = uvicorn.Server(uvicorn.Config(build_http_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield base
    server.should_exit = True
    thread.join(timeout=10)


async def _whoami(base: str, headers: dict):
    http = create_mcp_http_client(headers=headers)
    async with http, Client(streamable_http_client(f"{base}/mcp", http_client=http)) as client:
        return await client.call_tool("whoami", {})


def test_healthz(hosted):
    body = httpx.get(f"{hosted}/healthz").json()
    assert body["status"] == "ok" and body["service"] == "neuraleads-mcp"


async def test_bearer_key_selects_workspace(hosted, backend):
    res = await _whoami(hosted, {"Authorization": f"Bearer {backend['A']['keys']['read']}"})
    assert not res.is_error
    assert result_json(res)["tenant_id"] == backend["A"]["tenant_id"]


async def test_x_api_key_header_also_works(hosted, backend):
    res = await _whoami(hosted, {"X-API-Key": backend["B"]["keys"]["read"]})
    assert result_json(res)["tenant_id"] == backend["B"]["tenant_id"]


async def test_missing_key_never_falls_back_to_server_key(hosted):
    res = await _whoami(hosted, {})
    assert res.is_error
    assert "Missing API key" in "".join(c.text for c in res.content)


def test_foreign_host_header_rejected(hosted):
    r = httpx.post(f"{hosted}/mcp", headers={"Host": "evil.example", "Content-Type": "application/json",
                                             "Accept": "application/json, text/event-stream"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code in (400, 403, 421)
