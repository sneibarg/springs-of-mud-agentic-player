import re
from typing import Any, Callable, Optional

from net.rest.KmAnswer import KmAnswer


class KmError(Exception):
    """som-nlp-service rejected or did not answer a KM route."""


class KmClient:
    """REST bridge from this runtime to Knowledge Machine through som-nlp-service.

    `query` and `assert_expression` call the service session. Facts from a
    successful assertion stay there. `baseline` evaluates one question from
    the library that the service loaded at startup and does not keep the
    frames that question derived.
    """

    def __init__(self, base_url: str = "http://localhost:9081", query_path: str = "/km/query", assertions_path: str = "/km/assertions", baseline_path: str = "/km/baseline", request: Optional[Callable] = None, timeout_s: float = 120.0, players_path: str = "/km/players"):
        self.base_url = base_url.rstrip("/")
        self.query_path = _path(query_path)
        self.assertions_path = _path(assertions_path)
        self.baseline_path = _path(baseline_path)
        self.players_path = _path(players_path).rstrip("/")
        self._request = request or _default_request
        self.timeout_s = timeout_s

    def query(self, expression: str) -> KmAnswer:
        """POST /km/query. The service keeps a successful result."""
        return KmAnswer.from_json(self._send(self.query_path, {"expression": _required(expression)}))

    def assert_expression(self, expression: str) -> KmAnswer:
        """POST /km/assertions. A successful fact stays on the service session."""
        return KmAnswer.from_json(self._send(self.assertions_path, {"expression": _required(expression)}))

    def query_player(self, player: str, expression: str) -> KmAnswer:
        """Query the retained player situation. The service ensures it exists."""
        return self._player_result(player, "query", expression)

    def assert_player(self, player: str, expression: str) -> KmAnswer:
        """Assert into the retained player situation, preserving earlier facts."""
        return self._player_result(player, "assertions", expression)

    def _player_result(self, player: str, operation: str, expression: str) -> KmAnswer:
        if not isinstance(player, str) or not re.fullmatch(r"\*?[A-Za-z0-9][A-Za-z0-9_-]*", player) or player.lstrip("*").lower() == "global":
            raise KmError("Invalid KM player name")
        name = player.lstrip("*")
        return KmAnswer.from_json(self._send(f"{self.players_path}/{name}/{operation}", {"expression": _required(expression)}))

    def baseline(self, expressions: list[str]) -> list[KmAnswer]:
        """POST /km/baseline. One question, then the derived frames are dropped."""
        if not expressions:
            raise KmError("Expressions cannot be null or empty")
        body = {"expressions": [_required(expression) for expression in expressions]}
        payload = self._send(self.baseline_path, body)
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or not results:
            raise KmError("KM baseline returned no results")
        return [KmAnswer.from_json(item) for item in results]

    def _send(self, path: str, body: dict[str, Any]) -> dict:
        url = f"{self.base_url}{path}"
        try:
            response = self._request("POST", url, json=body, headers={"Content-Type": "application/json"}, timeout=self.timeout_s)
        except KmError:
            raise
        except Exception as exc:
            raise KmError(f"POST {url} failed: {exc.__class__.__name__}") from exc
        status = getattr(response, "status_code", 200)
        if status >= 400:
            raise KmError(_failure_message(response, url, status))
        payload = _json_object(response)
        if not isinstance(payload, dict):
            raise KmError(f"POST {url} returned no JSON object")
        return payload


def _required(expression: object) -> str:
    if not isinstance(expression, str) or not expression.strip():
        raise KmError("Expression cannot be null or empty")
    return expression


def _path(value: str) -> str:
    path = str(value or "").strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return path


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
