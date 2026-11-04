# World Knowledge API

When command bootstrap finishes, and again after the full snapshot, `KnowledgeClient` saves the document on som-server-modulith, port `9080`. The origin is `api.base_url` in `resources/agent.yml`. The default is `http://dragon:9080`.

- `PUT {api.base_url}{knowledge.path}/{characterId}` replaces one character's snapshot.
- `GET` the same path returns that document. `404` means nothing is stored.
- Send the login `Authorization` header. Leave the token out of the body and out of logs.
- The body is camelCase JSON from `WorldKnowledge.to_document`: `characterId`, `characterName`, `agentName`, `loginLines`, `helpTopics`, `commands`, `areas`, `mobiles`, `npcs`, `players`, and `room`. `commands` keeps `name`, `category`, and `helpText` in server order. Mobiles, npcs, and players include `auras`. `room.items` is a list of `{name, line, source}`. Bootstrap leaves that list empty. Look-prompt items stay on working memory, and only when `bootstrap.defer` is false and the look prompt is sent. Server `itemLines` are still stored.
- `characterId` in the body matches the path. A PUT replaces the whole snapshot.

`resources/agent.yml` `knowledge.path` is the path. The default is `/api/v1/agent-knowledge`. A failed save is reported and the telnet session continues.
