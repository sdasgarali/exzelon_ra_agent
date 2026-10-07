"""Shared fixtures.

Unit tests mock the REST API with respx. The ``backend`` fixture starts the
real NeuraLeads API (uvicorn, throwaway SQLite file) with the backend's own
virtualenv — the backend and the MCP SDK need different pydantic versions, so
they cannot share a process — and seeds two workspaces. Integration tests are
skipped when that virtualenv isn't available.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO / "backend"


def _backend_python() -> Path | None:
    override = os.environ.get("NEURALEADS_BACKEND_PYTHON")
    if override:
        return Path(override)
    for rel in ("venv/Scripts/python.exe", "venv/bin/python", ".venv/Scripts/python.exe", ".venv/bin/python"):
        p = BACKEND_DIR / rel
        if p.exists():
            return p
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def backend(tmp_path_factory):
    py = _backend_python()
    if py is None:
        pytest.skip("backend virtualenv not found (set NEURALEADS_BACKEND_PYTHON)")
    db_file = tmp_path_factory.mktemp("nl") / "e2e.db"
    port = _free_port()
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
           "DEBUG": "False",
           "SECRET_KEY": "mcp-e2e-secret-not-for-production",
           "ENCRYPTION_KEY": "kbt_mh7zLmsYjFAGgX_MAVtAousWEe7CQUtbNsi9m44=",
           "RATE_LIMIT_ENABLED": "false",
           "NEURALEADS_BACKEND_DIR": str(BACKEND_DIR),
           "PYTHONIOENCODING": "utf-8"}
    log = open(db_file.with_suffix(".log"), "w", encoding="utf-8")
    proc = subprocess.Popen([str(py), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=BACKEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 120
        while True:
            try:
                if httpx.get(f"{base}/api/v1/auth/me", timeout=2).status_code in (401, 403):
                    break
            except httpx.HTTPError:
                pass
            if proc.poll() is not None or time.time() > deadline:
                log.flush()
                pytest.fail("backend did not start; see " + str(db_file.with_suffix(".log")))
            time.sleep(1)
        seed = subprocess.run([str(py), str(Path(__file__).with_name("backend_seed.py"))], cwd=BACKEND_DIR,
                              env=env, capture_output=True, text=True, timeout=120)
        if seed.returncode != 0:
            pytest.fail(f"seed failed: {seed.stderr[-2000:]}")
        fixture = json.loads(seed.stdout.strip().splitlines()[-1])
        fixture["api_url"] = f"{base}/api/v1"
        yield fixture
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def result_json(res):
    """Decode a CallToolResult: structured content if present, else the JSON text block."""
    if res.structured_content is not None:
        sc = res.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads("".join(getattr(c, "text", "") for c in res.content))
