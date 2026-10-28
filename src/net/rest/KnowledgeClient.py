from typing import Any, Callable, Optional
from urllib.parse import quote


class KnowledgeStoreError(Exception):
    """The world-knowledge HTTP API rejected or did not answer a call."""


class KnowledgeClient:
    """Client for the agent world-knowledge API.

    The server side is not in this repository yet. It should implement:

    - `GET {base}{path}/{characterId}` returns the stored document, or 404 when none exists.
    - `PUT {base}{path}/{characterId}` replaces the stored document and returns it.
    - Both calls require the login `Authorization` header.
    - The body is the camelCase document produced by `WorldKnowledge.to_document`.
      `characterId` in the body matches the path. A PUT replaces the whole snapshot.
    """

    def __init__(
        self,
        base_url: str,
        path: str = "/api/v1/agent-knowledge",
        headers_provider: Optional[Callable[[], dict]] = None,
        request: Optional[Callable] = None,
        timeout_s: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.path = path if path.startswith("/") else f"/{path}"
        self._headers_provider = headers_provider or (lambda: {})
        self._request = request or _default_request
        self.timeout_s = timeout_s

    def save(self, character_id: str, document: dict[str, Any]) -> dict[str, Any]:
        body = dict(document)
        existing = body.get("characterId")
        if existing and existing != character_id:
            raise ValueError("characterId does not match the knowledge path")
        body["characterId"] = character_id
        response = self._call("PUT", character_id, body)
        if getattr(response, "content", None):
            payload = response.json()
            if isinstance(payload, dict):
                return payload
        return body

    def load(self, character_id: str) -> Optional[dict[str, Any]]:
        response = self._call("GET", character_id, None)
        if getattr(response, "status_code", None) == 404:
            return None
        _raise_for_status(response, "GET", self._url(character_id))
        payload = response.json()
        if not isinstance(payload, dict):
            raise KnowledgeStoreError(f"GET {self._url(character_id)} did not return a document")
        return payload

    def _call(self, method: str, character_id: str, body: Optional[dict]):
        url = self._url(character_id)
        try:
            response = self._request(
                method,
                url,
                json=body,
                headers=dict(self._headers_provider() or {}),
                timeout=self.timeout_s,
            )
        except KnowledgeStoreError:
            raise
        except Exception as exc:
            raise KnowledgeStoreError(f"{method} {url} failed: {exc.__class__.__name__}") from exc
        if method != "GET" or getattr(response, "status_code", None) != 404:
            _raise_for_status(response, method, url)
        return response

    def _url(self, character_id: str) -> str:
        return f"{self.base_url}{self.path}/{quote(str(character_id), safe='')}"


def _raise_for_status(response, method: str, url: str) -> None:
    status = getattr(response, "status_code", 200)
    if status >= 400:
        raise KnowledgeStoreError(f"{method} {url} failed with HTTP {status}")


def _default_request(method, url, json, headers, timeout):
    import requests

    return requests.request(method, url, json=json, headers=headers, timeout=timeout)
