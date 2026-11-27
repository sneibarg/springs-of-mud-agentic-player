# World Knowledge API

When command bootstrap finishes, and again after the full snapshot, `KnowledgeClient` saves the document on som-server-modulith, port `9080`. The origin is `api.base_url` in `resources/agent.yml`. The default is `http://dragon:9080`.

- `PUT {api.base_url}{knowledge.path}/{characterId}` replaces one character's snapshot.
- `GET` the same path returns that document. `404` means nothing is stored.
- Send the login `Authorization` header. Leave the token out of the body and out of logs.
- The body is camelCase JSON from `WorldKnowledge.to_document`: `characterId`, `characterName`, `agentName`, `loginLines`, `helpTopics`, `commands`, `areas`, `mobiles`, `npcs`, `players`, and `room`. `commands` keeps learned `name`, `category`, and `helpText` rows. Freshly observed names are ordered first in server order; historical/index-only descriptions can remain afterward and do not establish availability. Mobiles, npcs, and players include `auras`. `room.items` is a list of `{name, line, source}`. Bootstrap leaves that list empty. Look-prompt items stay on working memory, and only when `bootstrap.defer` is false and the look prompt is sent. Server `itemLines` are still stored.
- `characterId` in the body matches the path. A PUT replaces the whole snapshot.

`resources/agent.yml` `knowledge.path` is the path. The default is `/api/v1/agent-knowledge`. A failed save is reported and the telnet session continues.

`WorldKnowledge.commands` uses the shared CommandList/KnownCommand model. `command_records()` returns explicit stored rows only, and `summary` counts those same rows. `commands_from_help()` is an explicit legacy description fallback, never an executable list. `has_commands()` keeps the legacy bootstrap-skip decision for help-only documents; restoration still verifies availability with a fresh server request. Once a verb is observed, matching legacy help may fill its description.

Bootstrap now owns command categories and learned help on WorldKnowledge in both defer modes. The existing final snapshot save therefore includes those descriptions; defer controls model requests. The command-checkpoint callback runs in both modes after command help collection. Server help remains available even when enrichment fails. ObservationPipeline updates this local view alongside the session evidence queue. Bootstrap collection is separate from KM acceptance; the completion gate is documented in [First Login Knowledge](Bootstrap.md). Typed [evidence mapping plans](KmEvidence.md) now exist; full submission and acceptance remain step 7, with unsupported records retained explicitly. The REST JSON shape is unchanged, and no current-availability field is added to this document.
