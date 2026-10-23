"""Client for pm-mcp, the construction project-management server.

pm-mcp speaks the Model Context Protocol over HTTP (JSON-RPC with
Server-Sent-Event responses). The official ``mcp`` package would upgrade
Starlette past what this FastAPI version supports, so this is a small
dependency-free client: ``initialize`` once to get a session id, then
``tools/call`` per request. Tool results are JSON text.

Errors:
- ``PMError``: pm-mcp refused the request (unknown id, a gate not passed...);
  the message is pm-mcp's and is safe to show.
- ``PMUnavailable``: pm-mcp isn't reachable or answered with something that
  isn't MCP.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
# This app's name in pm-mcp's external links and activity log.
SYSTEM = "vr-construction"
ACTOR = "vr-backend"


class PMError(Exception):
    """pm-mcp refused the call; ``str(e)`` is its explanation."""


class PMUnavailable(Exception):
    """pm-mcp could not be reached."""


class PMClient:
    def __init__(self, url: str, timeout: float = 15.0, transport: Optional[httpx.BaseTransport] = None):
        self.url = url
        self._http = httpx.Client(timeout=timeout, transport=transport)
        self._session_id: Optional[str] = None
        self._next_id = 0
        self._lock = threading.Lock()

    def close(self) -> None:
        self._http.close()

    # -- protocol -----------------------------------------------------------

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL_VERSION}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post(self, payload: dict) -> httpx.Response:
        try:
            return self._http.post(self.url, json=payload, headers=self._headers())
        except httpx.HTTPError as e:
            raise PMUnavailable(f"pm-mcp is not reachable at {self.url} ({e.__class__.__name__})") from e

    @staticmethod
    def _parse(response: httpx.Response) -> dict:
        """The JSON-RPC message in a JSON or Server-Sent-Event body."""
        if "text/event-stream" in response.headers.get("content-type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    message = json.loads(line[5:].strip())
                    if "id" in message:
                        return message
            raise PMUnavailable("pm-mcp sent an event stream without a reply")
        return response.json()

    def _request(self, method: str, params: dict) -> dict:
        self._next_id += 1
        response = self._post({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params})
        if response.status_code in (400, 404) and self._session_id:
            raise _SessionExpired()
        if response.status_code >= 400:
            raise PMUnavailable(f"pm-mcp answered HTTP {response.status_code}")
        message = self._parse(response)
        if "error" in message:
            raise PMUnavailable(f"pm-mcp protocol error: {message['error'].get('message')}")
        return message["result"]

    def _initialize(self) -> None:
        self._session_id = None
        self._next_id += 1
        response = self._post({
            "jsonrpc": "2.0", "id": self._next_id, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                       "clientInfo": {"name": SYSTEM, "version": "1"}},
        })
        if response.status_code >= 400:
            raise PMUnavailable(f"pm-mcp answered HTTP {response.status_code} to initialize")
        self._parse(response)
        self._session_id = response.headers.get("mcp-session-id")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    # -- tools --------------------------------------------------------------

    def call(self, tool: str, **arguments: Any) -> Any:
        """Call a pm-mcp tool and return its decoded result."""
        args = {k: v for k, v in arguments.items() if v is not None}
        with self._lock:
            for attempt in (1, 2):
                if self._session_id is None:
                    self._initialize()
                try:
                    result = self._request("tools/call", {"name": tool, "arguments": args})
                    break
                except _SessionExpired:
                    # pm-mcp restarted and forgot the session: start a new one once.
                    self._session_id = None
                    if attempt == 2:
                        raise PMUnavailable("pm-mcp keeps rejecting the session")
        text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            # pm-mcp prefixes refusals with "Error executing tool <name>: ".
            raise PMError(text.split(": ", 1)[1] if text.startswith("Error executing tool") else text)
        if result.get("structuredContent") is not None:
            sc = result["structuredContent"]
            return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc
        return json.loads(text) if text else None


class _SessionExpired(Exception):
    pass


_client: Optional[PMClient] = None
_client_lock = threading.Lock()


def get_pm() -> PMClient:
    """The shared client (FastAPI dependency; tests override it)."""
    global _client
    with _client_lock:
        if _client is None:
            _client = PMClient(settings.pm_mcp_url, settings.pm_mcp_timeout_seconds)
        return _client
