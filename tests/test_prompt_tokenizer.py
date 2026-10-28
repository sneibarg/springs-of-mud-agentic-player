import os
import sys
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from prompt.Prompt import Prompt, PromptSubmission
from prompt.PromptCollection import PromptCollection


ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "resources" / "collections" / "SOMDB.Prompts.json"

SCORE = "\n".join(
    [
        "You are Example the new one, level 12, 17 years old (3 hours).",
        "You have scored 1200 exp, and have 10 gold and 40 silver coins.",
        "You need 50 exp to level.",
        "You are armored against piercing.",
        "You are armored against bashing.",
        "You are armored against slashing.",
        "You are armored against magic.",
        "<20hp 100m 100mv>",
    ]
)


class TestPromptTokenizer(unittest.TestCase):
    def setUp(self):
        self.score = PromptCollection.load(PROMPTS).get("score")

    def test_collection_keeps_the_score_intent_tokens(self):
        self.assertEqual(self.score.model, "gpt-oss:20b")
        self.assertEqual(self.score.tokens["expToLevel"]["text"], "the experience needed to level")
        self.assertEqual(self.score.tokens["armorClass"]["text"], "armor class")
        self.assertIn("{intent}", self.score.system)
        self.assertIn("{response}", self.score.system)
        self.assertEqual(self.score.user, "{score}")

    def test_experience_intent_is_filled_before_submission(self):
        submission = self.score.tokenize(SCORE, "expToLevel")

        self.assertEqual(submission.model, "gpt-oss:20b")
        self.assertEqual(submission.intents, ("expToLevel",))
        self.assertIn("Request: the experience needed to level", submission.system)
        self.assertIn('"expToLevel": 800', submission.system)
        self.assertNotIn('"armorPierce"', submission.system)
        self.assertNotIn("{intent}", submission.system)
        self.assertNotIn("{response}", submission.system)
        self.assertEqual(submission.user, SCORE)
        self.assertEqual(submission.json_schema["required"], ["expToLevel"])
        self.assertEqual(list(submission.json_schema["properties"]), ["expToLevel"])
        body = submission.to_request()
        self.assertEqual(list(body), ["model", "system", "user", "jsonSchema"])
        self.assertEqual(body["model"], "gpt-oss:20b")
        self.assertEqual(body["user"], SCORE)
        self.assertEqual(body["jsonSchema"]["required"], ["expToLevel"])
        self.assertNotIn("intents", body)
        self.assertEqual(submission.read_completion('{"expToLevel": 50}'), {"expToLevel": 50})
        self.assertEqual(submission.read_completion({"text": '{"expToLevel": 50}'}), {"expToLevel": 50})

    def test_armor_class_intent_asks_only_for_armor(self):
        submission = self.score.tokenize(["You are armored against piercing."], "armorClass")

        self.assertEqual(submission.user, "You are armored against piercing.")
        self.assertEqual(
            submission.json_schema["required"],
            [
                "armorPierce",
                "armorBash",
                "armorSlash",
                "armorMagic",
                "acPierce",
                "acBash",
                "acSlash",
                "acMagic",
            ],
        )
        self.assertNotIn("expToLevel", submission.json_schema["properties"])

    def test_several_intents_keep_selection_order(self):
        submission = self.score.tokenize(SCORE, "expToLevel", "armorClass")

        self.assertEqual(submission.intents, ("expToLevel", "armorClass"))
        self.assertIn(
            "Request: the experience needed to level, armor class",
            submission.system,
        )
        self.assertEqual(submission.json_schema["required"][0], "expToLevel")
        self.assertIn("acPierce", submission.json_schema["required"])

    def test_every_token_renders_without_leaving_placeholders(self):
        for name in self.score.tokens:
            submission = self.score.tokenize("You need 1 exp to level.", name)
            self.assertNotIn("{intent}", submission.system)
            self.assertNotIn("{response}", submission.system)
            self.assertNotIn("{score}", submission.user)
            self.assertTrue(submission.json_schema["required"])

    def test_blank_user_is_rejected_before_the_ollama_call(self):
        submission = self.score.tokenize("   ", "expToLevel")
        with self.assertRaises(ValueError) as raised:
            submission.to_request()
        self.assertEqual(str(raised.exception), "User prompt cannot be null or empty")

    def test_plain_completion_returns_the_text(self):
        submission = PromptSubmission("note", "", "  ", "Hello", {}, ())
        self.assertEqual(submission.to_request(), {"user": "Hello"})
        self.assertEqual(submission.read_completion({"text": "ok"}), "ok")
        with self.assertRaises(ValueError) as raised:
            submission.read_completion("  ")
        self.assertEqual(str(raised.exception), "Ollama returned an empty response")

    def test_schema_completion_must_be_json(self):
        submission = self.score.tokenize(SCORE, "expToLevel")
        with self.assertRaises(ValueError) as raised:
            submission.read_completion("not json")
        self.assertEqual(str(raised.exception), "Ollama completion was not JSON")

    def test_missing_or_unknown_intent_is_rejected(self):
        with self.assertRaises(ValueError):
            self.score.tokenize(SCORE)
        with self.assertRaises(ValueError):
            self.score.tokenize(SCORE, "not-a-score-fact")
        with self.assertRaises(ValueError):
            self.score.tokenize(SCORE, "gold", "gold")

    def test_a_prompt_without_tokens_is_not_submitted(self):
        exits = PromptCollection.load(PROMPTS).get("exits")
        with self.assertRaises(ValueError):
            exits.tokenize("north", "expToLevel")

    def test_inline_prompt_rejects_a_key_outside_the_schema(self):
        prompt = Prompt(
            name="score",
            model="gpt-oss:20b",
            system="Request: {intent}\n{response}",
            user="{score}",
            json_schema={"type": "object", "properties": {"expToLevel": {"type": "integer"}}},
            tokens={"expToLevel": {"text": "the experience needed to level", "example": {"missing": 1}}},
        )
        with self.assertRaises(ValueError):
            prompt.tokenize("You need 1 exp to level.", "expToLevel")


if __name__ == "__main__":
    unittest.main()
