import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.ConnectionCatalog import ConnectionCatalog, deobfuscate_password, obfuscate_password


ROOT = Path(__file__).resolve().parents[1]


class TestConnectionCatalog(unittest.TestCase):
    def test_password_roundtrip_matches_the_ui(self):
        stored = obfuscate_password("secret")
        self.assertEqual(deobfuscate_password(stored), "secret")
        self.assertEqual(deobfuscate_password(""), "")
        self.assertEqual(deobfuscate_password("not-base64"), "")

    def test_saved_connections_keep_the_password_obfuscated(self):
        path = ROOT / "resources" / "connections.json"
        catalog = ConnectionCatalog.load(path)
        primary = catalog.named("springsofmud")
        alternate = catalog.named("SpringsOfMUD-alt")
        text = path.read_text(encoding="utf-8")

        self.assertEqual(primary.account_name, "sneibarg")
        self.assertEqual(primary.server_url, "http://localhost:8169")
        self.assertEqual(primary.telnet_host, "malboji")
        self.assertEqual(primary.telnet_port, 6969)
        self.assertEqual(primary.obfuscated_password, "Y2hhbmdlaXQ=")
        self.assertNotEqual(primary.login_password(), primary.obfuscated_password)
        self.assertNotIn(primary.login_password(), text)
        self.assertEqual(alternate.account_name, "neibarge")
        self.assertIsNone(alternate.telnet_host)
        self.assertIsNone(alternate.telnet_port)

    def test_missing_connection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "connections.json"
            path.write_text(json.dumps([
                {
                    "name": "Local",
                    "server_url": "http://localhost:8169",
                    "account_name": "ada",
                    "password": obfuscate_password("secret"),
                }
            ]), encoding="utf-8")
            catalog = ConnectionCatalog.load(path)
            with self.assertRaises(LookupError):
                catalog.named("missing")


if __name__ == "__main__":
    unittest.main()
