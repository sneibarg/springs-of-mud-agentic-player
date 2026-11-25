import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net.rest.KmClient import KmClient, KmError


class _Response:
    def __init__(self, status_code=200, payload=None, content=b"{}"):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class TestKmClient(unittest.TestCase):
    def test_query_and_assert_post_to_the_nlp_service(self):
        captured = []

        def request(method, url, json, headers, timeout):
            captured.append((method, url, json, headers, timeout))
            return _Response(payload={"ok": True, "answer": "(red)", "errors": []})

        client = KmClient("http://dragon:9081/", request=request)
        answer = client.query("(the color of Fred)")
        asserted = client.assert_expression("(Fred has (color (red)))")

        self.assertEqual(answer.answer, "(red)")
        self.assertEqual(asserted.answer, "(red)")
        self.assertEqual(captured[0][0], "POST")
        self.assertEqual(captured[0][1], "http://dragon:9081/km/query")
        self.assertEqual(captured[0][2], {"expression": "(the color of Fred)"})
        self.assertEqual(captured[1][1], "http://dragon:9081/km/assertions")
        self.assertEqual(captured[0][3], {"Content-Type": "application/json"})
        self.assertEqual(captured[0][4], 120.0)

    def test_baseline_posts_the_question_and_returns_every_result(self):
        captured = {}

        def request(method, url, json, headers, timeout):
            captured.update(url=url, json=json)
            return _Response(payload={"ok": True, "results": [{"ok": True, "answer": "(*Goal)", "errors": []}, {"ok": True, "answer": "(steady)", "errors": []}]})

        client = KmClient("http://dragon:9081", request=request)
        answers = client.baseline(["(*Goal has (instance-of (Som-Level-Goal)))", "(the som-notch of *View)"])

        self.assertEqual(captured["url"], "http://dragon:9081/km/baseline")
        self.assertEqual(captured["json"]["expressions"][1], "(the som-notch of *View)")
        self.assertEqual([item.answer for item in answers], ["(*Goal)", "(steady)"])

    def test_service_error_is_the_message_and_a_blank_expression_is_not_sent(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=400, payload={"error": "Invalid expression"}, content=b"secret")

        client = KmClient("http://dragon:9081", request=request)
        with self.assertRaises(KmError) as raised:
            client.query("(bad)")
        self.assertEqual(str(raised.exception), "Invalid expression")
        self.assertNotIn("secret", str(raised.exception))
        with self.assertRaises(KmError) as blank:
            client.baseline(["(ok)", "  "])
        self.assertEqual(str(blank.exception), "Expression cannot be null or empty")

    def test_not_ported_uses_the_service_message(self):
        def request(method, url, json, headers, timeout):
            return _Response(status_code=501, payload={"error": "Command is not ported"})

        client = KmClient("http://dragon:9081", request=request)
        with self.assertRaises(KmError) as raised:
            client.assert_expression("(anonymous-instancep Fred)")
        self.assertEqual(str(raised.exception), "Command is not ported")


if __name__ == "__main__":
    unittest.main()
