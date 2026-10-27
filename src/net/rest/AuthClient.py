from typing import Callable, Dict, Optional
from urllib.parse import urljoin

from net.rest.AuthResponse import AuthResponse


class AuthClient:
    """Login client aligned with springs-of-mud-ui AuthClient.

    The auth token is the Authorization response header from POST /api/auth/login.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8169",
        login_path: str = "/api/auth/login",
        post: Optional[Callable] = None,
        timeout_s: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.login_path = login_path if login_path.startswith("/") else f"/{login_path}"
        self.auth_endpoint = urljoin(f"{self.base_url}/", self.login_path.lstrip("/"))
        self._post = post or _default_post
        self.timeout_s = timeout_s
        self.jwt_token: Optional[str] = None
        self.auth_data: Optional[AuthResponse] = None

    def login(self, account_name: str, password: str) -> AuthResponse:
        response = self._post(
            self.auth_endpoint,
            json={"accountName": account_name, "password": password},
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        self.auth_data = AuthResponse.from_json(response.json())
        self.jwt_token = _authorization_header(response.headers)
        return self.auth_data

    def get_auth_headers(self) -> Dict[str, str]:
        if not self.jwt_token:
            return {}
        token = self.jwt_token
        if token.lower().startswith("bearer "):
            return {"Authorization": token}
        return {"Authorization": f"Bearer {token}"}

    def is_authenticated(self) -> bool:
        return self.auth_data is not None and bool(self.jwt_token)

    def logout(self) -> None:
        self.jwt_token = None
        self.auth_data = None


def _authorization_header(headers) -> Optional[str]:
    if headers is None:
        return None
    if "Authorization" in headers:
        return headers["Authorization"]
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    return getter("Authorization")


def _default_post(url, json, timeout):
    import requests

    return requests.post(url, json=json, timeout=timeout)
