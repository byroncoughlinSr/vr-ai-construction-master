"""A real pm-mcp server for the tests, started once per test run.

The construction plan lives in pm-mcp, so tests of the schedule, budget and
compliance routes talk to an actual pm-mcp over HTTP with a throwaway database.
It needs pm-mcp installed (``/development/pm-mcp/.venv/bin/pm-mcp``, or set
``PM_MCP_COMMAND``); tests that use it are skipped when it isn't.

Use ``use_pm()`` in a fixture: it points the app's client (``get_pm``) at the
server and returns that client.
"""

import atexit
import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid

import httpx
import pytest

from app.services import pm_client

_COMMAND = os.environ.get("PM_MCP_COMMAND", "/development/pm-mcp/.venv/bin/pm-mcp")
_server: dict = {}


def _start() -> str:
    if "url" in _server:
        return _server["url"]
    if not (os.path.exists(_COMMAND) or shutil.which(_COMMAND)):
        pytest.skip(f"pm-mcp is not installed ({_COMMAND})")
    workdir = tempfile.mkdtemp(prefix="pm-mcp-tests-")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    process = subprocess.Popen(
        [_COMMAND, "--transport", "streamable-http", "--port", str(port), "--db", os.path.join(workdir, "pm.db")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            httpx.post(url, json={}, timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        process.kill()
        pytest.fail("pm-mcp did not start")

    def stop():
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(workdir, ignore_errors=True)

    atexit.register(stop)
    _server["url"] = url
    return url


def use_pm() -> pm_client.PMClient:
    """Point ``get_pm`` at the test server; returns the client."""
    client = pm_client.PMClient(_start())
    pm_client._client = client
    return client


def release_pm() -> None:
    if pm_client._client is not None:
        pm_client._client.close()
    pm_client._client = None


def unique(name: str) -> str:
    """Project names are unique in pm-mcp, which outlives each test's database."""
    return f"{name} {uuid.uuid4().hex[:6]}"
