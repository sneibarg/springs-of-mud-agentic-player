import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import _log_directory, configure_logging


class TestLogging(unittest.TestCase):
    def tearDown(self):
        self._release_log_files()

    def _release_log_files(self):
        root = logging.getLogger()
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)

    def test_startup_writes_an_info_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = configure_logging(tmp)
            try:
                logging.getLogger("play.Bootstrapper").info("Reading areas, players, and the current room.")
                for handler in logging.getLogger().handlers:
                    handler.flush()
                text = Path(path).read_text(encoding="utf-8")
            finally:
                self._release_log_files()
        self.assertEqual(os.path.basename(path), "agent.log")
        self.assertIn("Log file", text)
        self.assertIn("[INFO]", text)
        self.assertIn("play.Bootstrapper", text)
        self.assertIn("Reading areas, players, and the current room.", text)

    def test_log_directory_sits_beside_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_log_directory(os.path.join(tmp, "resources", "agent.yml")), os.path.join(tmp, "log"))
            self.assertEqual(_log_directory(os.path.join(tmp, "agent.yml")), os.path.join(tmp, "log"))


if __name__ == "__main__":
    unittest.main()
