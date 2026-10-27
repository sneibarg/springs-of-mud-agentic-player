import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.AuthClient import AuthClient


class _Response:
    def __init__(self, payload, headers, status_code=200):
        self._payload = payload
        self.headers = headers
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TestAuthClient(unittest.TestCase):
    def test_login_stores_authorization_token_and_characters(self):
        captured = {}

        def post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return _Response(
                {
                    "id": "account-1",
                    "firstName": "Ada",
                    "lastName": "Lovelace",
                    "accountName": "ada",
                    "emailAddress": "ada@example.com",
                    "password": "secret",
                    "playerCharacterList": [
                        {"id": "char-1", "name": "Example"},
                        {"id": "char-2", "name": "Other"},
                    ],
                },
                {"Authorization": "jwt-token"},
            )

        client = AuthClient("http://localhost:8169/", post=post)
        auth = client.login("ada", "secret")

        self.assertEqual(captured["url"], "http://localhost:8169/api/auth/login")
        self.assertEqual(captured["json"], {"accountName": "ada", "password": "secret"})
        self.assertEqual(client.jwt_token, "jwt-token")
        self.assertEqual(client.get_auth_headers(), {"Authorization": "Bearer jwt-token"})
        self.assertTrue(client.is_authenticated())
        self.assertEqual(auth.character_named("example").id, "char-1")
        self.assertFalse(hasattr(auth, "password"))

    def test_bearer_prefix_is_not_doubled(self):
        def post(url, json, timeout):
            return _Response(
                {"id": "account-1", "accountName": "ada", "playerCharacterList": []},
                {"Authorization": "Bearer already"},
            )

        client = AuthClient(post=post)
        client.login("ada", "secret")
        self.assertEqual(client.get_auth_headers(), {"Authorization": "Bearer already"})


if __name__ == "__main__":
    unittest.main()
