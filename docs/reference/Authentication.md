# Authentication And Telnet

1. `connect <connection-name>` loads that entry from `resources/connections.json`. The password field is base64, matching `springs-of-mud-ui` `ConnectionSettings._deobfuscate_password`. `AuthClient.login(account_name, password)` posts `{"accountName", "password"}` to the connection `server_url` plus `/api/auth/login`.
2. The auth token is the `Authorization` response header. `get_auth_headers()` sends it as a Bearer token for later REST calls. A value that already starts with `Bearer ` is not prefixed again.
3. The login body supplies `id` and `playerCharacterList`. `list` prints those character names. `logon <characterName>` accepts only one of those names. `PlayerSession` then connects with `TelnetClient` and sends one line:

```text
logon {"accountId":"<account id>","characterId":"<character id>","characterName":"<name>"}
```

That line is the contract in `springs-of-mud-server` `MessageCodec`: a `logon ` prefix plus JSON becomes `MessageType.AUTH`. The game server currently accepts `accountId`, `characterId`, and `characterName`. Keep the JWT off the telnet line so it does not land in game logs. Hold it on `AuthClient` for REST calls.

Default ports match the UI client: auth `http://localhost:8169`, telnet `localhost:6969`. Override them in `resources/agent.yml`.
