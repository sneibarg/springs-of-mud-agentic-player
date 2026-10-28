# springs-of-mud-agentic-player

Python runtime for Springs of MUD agentic player characters.

Agents are documents in the `SOMDB` collection `Agents`. This repository loads that collection from `resources/collections/SOMDB.Agents.json`.

The runtime logs in through the same `/api/auth/login` endpoint as `springs-of-mud-ui`. Saved accounts are in `resources/connections.json`, with the password obfuscated the same way as the UI. After `connect`, `logon` accepts only a character from that account. `Bootstrapper` then reads the available help pages and records areas, mobiles, non-player characters, and other players.

## Setup

```powershell
pip install -r requirements.txt
```

## Run

From the repository root, start an agent named in `SOMDB.Agents.json`:

```powershell
$env:PYTHONPATH = "src"
python -m main --list
python -m main --agent example-agent
```

The process starts idle and listens on `127.0.0.1:9711`. From another shell, send one command at a time:

```powershell
$env:PYTHONPATH = "src"
python -m cli connect SpringsOfMUD
python -m cli list
python -m cli logon <character>
python -m cli play
```

`logon` accepts only a character printed by `list`. The CLI and the listener accept only `idle`, `play`, `list`, `connect <name>`, `logon <name>`, `memory [path]`, and `output [on|off|file [off|path]]`. `python src/main.py --list` works without `PYTHONPATH`.

Auth URL and telnet host defaults live in `resources/agent.yml`. A saved connection supplies its own server URL and telnet host. Defaults are auth `http://localhost:8169` and telnet `localhost:6969`.

## Test

```powershell
python -m unittest discover -s tests
```
