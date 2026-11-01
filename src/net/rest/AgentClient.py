from typing import Any, Callable, Optional
from urllib.parse import quote


class AgentStoreError(Exception):
    """The agent HTTP API rejected or did not answer a call."""


class AgentClient:
    """Client for GET /api/v1/agents on som-server-modulith.

    `list` returns the JSON array. `get` returns one document, or None on 404.
    Name lookup on the server ignores case. The runtime does not PUT agents.
    """

    def __init__(self, base_url: str, path: str = "/api/v1/agents", headers_provider: Optional[Callable[[], dict]] = None, request: Optional[Callable] = None, timeout_s: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.path = path if path.startswith("/") else f"/{path}"
        self._headers_provider = headers_provider or (lambda: {})
        self._request = request or _default_request
        self.timeout_s = timeout_s

    def list(self) -> list:
        response = self._call("GET", None, allow_missing=False)
        payload = response.json()
        if not isinstance(payload, list):
            raise AgentStoreError(f"GET {self._url(None)} did not return a document list")
        return payload

    def get(self, name: str) -> Optional[dict[str, Any]]:
        cleaned = str(name or "").strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        response = self._call("GET", cleaned, allow_missing=True)
        if getattr(response, "status_code", None) == 404:
            return None
        _raise_for_status(response, "GET", self._url(cleaned))
        payload = response.json()
        if not isinstance(payload, dict):
            raise AgentStoreError(f"GET {self._url(cleaned)} did not return a document")
        return payload

    def _call(self, method: str, name: Optional[str], *, allow_missing: bool):
        url = self._url(name)
        try:
            response = self._request(method, url, json=None, headers=dict(self._headers_provider() or {}), timeout=self.timeout_s)
        except AgentStoreError:
            raise
        except Exception as exc:
            raise AgentStoreError(f"{method} {url} failed: {exc.__class__.__name__}") from exc
        if not (allow_missing and getattr(response, "status_code", None) == 404):
            _raise_for_status(response, method, url)
        return response

    def _url(self, name: Optional[str]) -> str:
        if name is None:
            return f"{self.base_url}{self.path}"
        return f"{self.base_url}{self.path}/{quote(str(name), safe='')}"


def _raise_for_status(response, method: str, url: str) -> None:
    status = getattr(response, "status_code", 200)
    if status >= 400:
        raise AgentStoreError(f"{method} {url} failed with HTTP {status}")


def _default_request(method, url, json, headers, timeout):
    import requests

    return requests.request(method, url, json=json, headers=headers, timeout=timeout)
