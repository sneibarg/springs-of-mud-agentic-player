# springs-of-mud-agentic-player

Python runtime for Springs of MUD agentic player characters.

Agents are documents in the `SOMDB` collection `Agents`. This repository loads that collection from `resources/collections/SOMDB.Agents.json`.

The runtime logs in through the same `/api/auth/login` endpoint as `springs-of-mud-ui`, keeps the `Authorization` token, opens a telnet session to the game server, and sends the `logon` payload for the agent's character.

## Setup

```powershell
pip install -r requirements.txt
```

## Run

From the repository root, set the account password and start an agent named in `SOMDB.Agents.json`:

```powershell
$env:PYTHONPATH = "src"
$env:SOM_ACCOUNT_PASSWORD = "<account password>"
python -m main --list
python -m main --agent example-agent
```

`python src/main.py --list` works without `PYTHONPATH`.

Auth URL and telnet host live in `resources/agent.yml`. Defaults are auth `http://localhost:8169` and telnet `localhost:6969`.

## Test

```powershell
python -m unittest discover -s tests
```
