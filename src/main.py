import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.AgentCollection import AgentCollection
from agent.AgentConfig import AgentConfig
from agent.AgentRegistry import AgentRegistry
from control.GameplayOutput import GameplayOutput
from control.PlayerControl import PlayerControl
from memory.WorkingMemory import WorkingMemory
from net.AccountSession import AccountSession
from net.local.ControlServer import ControlServer
from net.rest.AuthClient import AuthClient
from net.rest.ConnectionCatalog import ConnectionCatalog
from net.rest.KnowledgeClient import KnowledgeClient, KnowledgeStoreError
from net.telnet.PlayerSession import PlayerSession
from net.telnet.TelnetClient import TelnetConfig
from play.Bootstrapper import Bootstrapper
from play.PlayError import PlayError


logger = logging.getLogger(__name__)


def default_config_path() -> str:
    cwd_candidate = os.path.join(os.getcwd(), "resources", "agent.yml")
    if os.path.exists(cwd_candidate):
        return cwd_candidate
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "agent.yml")


def list_agents(registry: AgentRegistry) -> None:
    for agent in registry.all():
        state = "enabled" if agent.enabled else "disabled"
        print(f"{agent.name}\t{state}\t{agent.account_name}/{agent.character_name}")


def run_agent(agent_name: str, config: AgentConfig) -> int:
    collection = AgentCollection.load(config.collection_path)
    registry = AgentRegistry(collection.agents)
    agent = registry.require(agent_name)
    catalog = ConnectionCatalog.load(config.connections_path)
    output = GameplayOutput()
    account = AccountSession(
        catalog,
        auth_base_url=config.auth_base_url,
        login_path=config.login_path,
        telnet_host=config.telnet_host,
        telnet_port=config.telnet_port,
        auth_client_factory=lambda base_url: AuthClient(base_url, login_path=config.login_path),
        session_factory=lambda host, port: PlayerSession(
            TelnetConfig(host=host, port=port),
            on_line=output.write,
        ),
    )
    memory = WorkingMemory()
    control = PlayerControl(memory=memory, output=output, account=account)
    server = ControlServer(control, host=config.control_host, port=config.control_port)
    try:
        server.start()
        print(f"Control listening on {server.host}:{server.bound_port}", flush=True)
        control.drive(
            lambda: _begin_play(account, registry, agent, config, memory),
            connected=lambda: account.session is None or account.session.client.connected,
        )
    except PlayError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        server.stop()
        control.stop()
        output.close()
        account.close()
    return 0


def _begin_play(account: AccountSession, registry, agent, config, memory) -> None:
    if not account.logged_on:
        print("Log on with an available character before play.", file=sys.stderr)
        return
    character = account.character
    knowledge = Bootstrapper(
        account.session,
        [item.character_name for item in registry.all()],
        character.name,
        memory=memory,
        replace_existing=config.telnet_replace_existing,
    ).bootstrap()
    memory.absorb_world(knowledge)
    _save_knowledge(config, account.auth_client, character.id, knowledge.to_document(
        character_id=character.id,
        character_name=character.name,
        agent_name=agent.name,
    ))
    room_name = knowledge.room.name if knowledge.room is not None else ""
    print(
        "Knowledge: "
        f"{len(knowledge.help_topics)} help, "
        f"{len(knowledge.areas)} areas, "
        f"{len(knowledge.mobiles)} mobiles, "
        f"{len(knowledge.npcs)} npcs, "
        f"{len(knowledge.players)} players."
    )
    if room_name:
        print(f"Current room: {room_name}")


def _save_knowledge(config: AgentConfig, auth_client: AuthClient, character_id: str, document: dict) -> None:
    client = KnowledgeClient(
        config.knowledge_base_url,
        path=config.knowledge_path,
        headers_provider=auth_client.get_auth_headers,
    )
    try:
        client.save(character_id, document)
    except (KnowledgeStoreError, ValueError) as exc:
        logger.warning("World knowledge was not saved: %s", exc)
        print(f"World knowledge was not saved: {exc}", file=sys.stderr)


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
