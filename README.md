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

The process starts idle, writes `log/agent.log` beside the repository, and listens on `127.0.0.1:9711`. `bootstrap.initial` in `resources/agent.yml` connects the saved account for that agent, logs on its character, and runs bootstrap before waiting for control commands. From another shell, send one command at a time:

```powershell
$env:PYTHONPATH = "src"
python -m cli connect SpringsOfMUD
python -m cli list
python -m cli logon <character>
python -m cli play
```

`logon` accepts only a character printed by `list`. The CLI and the listener accept only `idle`, `play`, `list`, `connect <name>`, `logon <name>`, `memory [path]`, and `output [on|off|file [off|path]]`. `python src/main.py --list` works without `PYTHONPATH`.

Auth is `auth.base_url` and `auth.login_path` in `resources/agent.yml`. A saved connection does not replace that URL. Its telnet host is used when it names one.

## Test

```powershell
python -m unittest discover -s tests
```
