import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.AgentCollection import AgentCollection
from agent.AgentConfig import AgentConfig
from agent.AgentRegistry import AgentRegistry
from net.rest.AuthClient import AuthClient
from net.telnet.PlayerSession import PlayerSession
from net.telnet.TelnetClient import TelnetConfig


PASSWORD_ENV = "SOM_ACCOUNT_PASSWORD"


def default_config_path() -> str:
    cwd_candidate = os.path.join(os.getcwd(), "resources", "agent.yml")
    if os.path.exists(cwd_candidate):
        return cwd_candidate
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "agent.yml")


def relay(session: PlayerSession) -> None:
    stop = threading.Event()

    def print_incoming() -> None:
        while not stop.is_set():
            line = session.client.poll_line()
            if line is not None:
                print(line, flush=True)
            elif not session.client.connected:
                break
            else:
                time.sleep(0.05)

    printer = threading.Thread(target=print_incoming, name="PlayerSession.printer", daemon=True)
    printer.start()
    print("Connected. Type commands, or press Ctrl+C to disconnect.", flush=True)
    try:
        while session.client.connected:
            text = input()
            session.client.send_line(text)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        stop.set()
        session.close()


def list_agents(registry: AgentRegistry) -> None:
    for agent in registry.all():
        state = "enabled" if agent.enabled else "disabled"
        print(f"{agent.name}\t{state}\t{agent.account_name}/{agent.character_name}")


def run_agent(agent_name: str, config: AgentConfig) -> int:
    collection = AgentCollection.load(config.collection_path)
    registry = AgentRegistry(collection.agents)
    agent = registry.require(agent_name)
    password = os.environ.get(PASSWORD_ENV, "")
    if not password:
        print(f"Set {PASSWORD_ENV} to the password for account {agent.account_name}.", file=sys.stderr)
        return 2

    auth_client = AuthClient(config.auth_base_url, login_path=config.login_path)
    auth = auth_client.login(agent.account_name, password)
    if not auth_client.jwt_token:
        print("Login succeeded without an Authorization token.", file=sys.stderr)
        return 2

    session = PlayerSession(TelnetConfig(host=config.telnet_host, port=config.telnet_port))
    session.connect()
    try:
        session.logon(auth, agent.character_name)
        relay(session)
    finally:
        session.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Connect a Springs of MUD agentic player.")
    parser.add_argument("--config", default=default_config_path(), help="Path to agent.yml")
    parser.add_argument("--agent", help="Agent name from SOMDB.Agents")
    parser.add_argument("--list", action="store_true", help="List agents and exit")
    args = parser.parse_args(argv)

    config = AgentConfig.load(args.config)
    if args.list or not args.agent:
        collection = AgentCollection.load(config.collection_path)
        list_agents(AgentRegistry(collection.agents))
        return 0
    return run_agent(args.agent, config)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, LookupError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
