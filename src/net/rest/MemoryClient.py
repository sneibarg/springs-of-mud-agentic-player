from typing import Any, Callable, Optional
from urllib.parse import quote


class MemoryStoreError(Exception):
    """The working-memory HTTP API rejected or did not answer a call."""


class MemoryClient:
    """Client for /api/v1/agent-memory/{agentName} on som-server-modulith.

    PUT replaces one agent's snapshot. The server sets `savedAt`. GET returns
    that document, or 404 when nothing is stored or the snapshot is past retention.
    `agentName` matches the path ignoring case.
    """

    def __init__(self, base_url: str, path: str = "/api/v1/agent-memory", headers_provider: Optional[Callable[[], dict]] = None, request: Optional[Callable] = None, timeout_s: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.path = path if path.startswith("/") else f"/{path}"
        self._headers_provider = headers_provider or (lambda: {})
        self._request = request or _default_request
        self.timeout_s = timeout_s

    def save(self, agent_name: str, document: dict[str, Any]) -> dict[str, Any]:
        cleaned = _required_name(agent_name)
        body = dict(document or {})
        existing = body.get("agentName")
        if existing is not None and not str(existing).strip():
            raise ValueError("agentName must not be blank")
        if str(existing or "").strip() and str(existing).strip().lower() != cleaned.lower():
            raise ValueError("agentName does not match the memory path")
        if not str(existing or "").strip():
            body["agentName"] = cleaned
        body.pop("savedAt", None)
        body.pop("id", None)
        response = self._call("PUT", cleaned, body, allow_missing=False)
        if getattr(response, "content", None):
            payload = response.json()
            if isinstance(payload, dict):
                return payload
        return body

    def load(self, agent_name: str) -> Optional[dict[str, Any]]:
        cleaned = _required_name(agent_name)
        response = self._call("GET", cleaned, None, allow_missing=True)
        if getattr(response, "status_code", None) == 404:
            return None
        _raise_for_status(response, "GET", self._url(cleaned))
        payload = response.json()
        if not isinstance(payload, dict):
            raise MemoryStoreError(f"GET {self._url(cleaned)} did not return a document")
        return payload

    def _call(self, method: str, agent_name: str, body: Optional[dict], *, allow_missing: bool):
        url = self._url(agent_name)
        try:
            response = self._request(method, url, json=body, headers=dict(self._headers_provider() or {}), timeout=self.timeout_s)
        except MemoryStoreError:
            raise
        except Exception as exc:
            raise MemoryStoreError(f"{method} {url} failed: {exc.__class__.__name__}") from exc
        if not (allow_missing and getattr(response, "status_code", None) == 404):
            _raise_for_status(response, method, url)
        return response

    def _url(self, agent_name: str) -> str:
        return f"{self.base_url}{self.path}/{quote(str(agent_name), safe='')}"


def _required_name(agent_name: str) -> str:
    cleaned = str(agent_name or "").strip()
    if not cleaned:
        raise ValueError("agentName must not be blank")
    return cleaned


def _raise_for_status(response, method: str, url: str) -> None:
    status = getattr(response, "status_code", 200)
    if status >= 400:
        raise MemoryStoreError(f"{method} {url} failed with HTTP {status}")


def _default_request(method, url, json, headers, timeout):
    import requests

    return requests.request(method, url, json=json, headers=headers, timeout=timeout)
