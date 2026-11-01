# Prompts

`SOMDB.Prompts.json` holds extractor prompts for model `gpt-oss:20b` and remains the unit-test fixture. A caller that needs a prompt loads it with `GET /api/v1/agent-prompts/{name}`. `bootstrap()` does not call those prompts. `score` asks for one or more intent tokens, such as `expToLevel` or `armorClass`. `Prompt.tokenize(score_text, *intents)` replaces `{intent}`, `{response}`, and `{score}` and narrows `jsonSchema` to those facts.

`PromptSubmission.to_request()` is the body for som-nlp-service `POST /ollama/completions`: `model`, `system`, `user`, and `jsonSchema`. A blank user is rejected with the service message and is not sent. `OllamaClient.complete` returns the `text` field. When the request included a schema, `read_completion` parses that text as JSON. `resources/agent.yml` `ollama.base_url` is `http://localhost:9081`.
