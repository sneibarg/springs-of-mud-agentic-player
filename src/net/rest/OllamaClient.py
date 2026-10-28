from typing import Any, Callable, Optional


class OllamaError(Exception):
    """som-nlp-service rejected or did not answer POST /ollama/completions."""


class OllamaClient:
    """Client for the som-nlp-service Ollama endpoint.

    POST {base}/ollama/completions with model, system, user, and jsonSchema.
    A blank model or system may be omitted. The user prompt is required.
    200 returns {"text": "..."}. 400 and 502 return {"error": "..."}.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:9081",
        path: str = "/ollama/completions",
        request: Optional[Callable] = None,
        timeout_s: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.path = path if path.startswith("/") else f"/{path}"
        self._request = request or _default_request
        self.timeout_s = timeout_s

    def complete(self, body: dict[str, Any]) -> str:
        user = body.get("user") if isinstance(body, dict) else None
        if not isinstance(user, str) or not user.strip():
            raise OllamaError("User prompt cannot be null or empty")
        url = f"{self.base_url}{self.path}"
        try:
            response = self._request(
                "POST",
                url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout_s,
            )
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaError(f"POST {url} failed: {exc.__class__.__name__}") from exc
        status = getattr(response, "status_code", 200)
        if status >= 400:
            raise OllamaError(_failure_message(response, url, status))
        payload = _json_object(response)
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise OllamaError("Ollama returned an empty response")
        return text


def _failure_message(response, url: str, status: int) -> str:
    payload = _json_object(response)
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, str) and error.strip():
        return error
    return f"POST {url} failed with HTTP {status}"


def _json_object(response) -> Any:
    if not getattr(response, "content", None):
        return None
    try:
        return response.json()
    except Exception:
        return None


def _default_request(method, url, json, headers, timeout):
    import requests

    return requests.request(method, url, json=json, headers=headers, timeout=timeout)
