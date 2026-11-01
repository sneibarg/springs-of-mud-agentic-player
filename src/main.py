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
from net.rest.AgentClient import AgentClient, AgentStoreError
from net.rest.AuthClient import AuthClient
from net.rest.ConnectionCatalog import ConnectionCatalog
from net.rest.KnowledgeClient import KnowledgeClient, KnowledgeStoreError
from net.rest.MemoryClient import MemoryClient, MemoryStoreError
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


def load_registry(config: AgentConfig) -> AgentRegistry:
    client = AgentClient(config.api_base_url, path=config.agents_path)
    source = f"{config.api_base_url}{config.agents_path}"
    collection = AgentCollection.from_documents(client.list(), source)
    return AgentRegistry(collection.agents)


def run_agent(agent_name: str, config: AgentConfig) -> int:
    registry = load_registry(config)
    agent = registry.require(agent_name)
    catalog = ConnectionCatalog.load(config.connections_path)
    output = GameplayOutput()
    account = AccountSession(catalog, auth_base_url=config.auth_base_url, login_path=config.login_path, telnet_host=config.telnet_host, telnet_port=config.telnet_port, auth_client_factory=lambda base_url: AuthClient(base_url, login_path=config.login_path), session_factory=lambda host, port: PlayerSession(TelnetConfig(host=host, port=port), on_line=output.write))
    memory_client = MemoryClient(config.api_base_url, path=config.memory_path, headers_provider=lambda: account.auth_client.get_auth_headers() if account.auth_client else {})
    memory, memory_ready = _load_memory(memory_client, agent.name)
    control = PlayerControl(memory=memory, output=output, account=account)
    server = ControlServer(control, host=config.control_host, port=config.control_port)
    played = False

    def on_play() -> None:
        nonlocal played
        played = _begin_play(account, registry, agent, config, memory, memory_client, memory_ready)

    try:
        server.start()
        print(f"Control listening on {server.host}:{server.bound_port}", flush=True)
        control.drive(on_play, connected=lambda: account.session is None or account.session.client.connected)
    except PlayError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if played and memory_ready:
            _save_memory(memory_client, agent.name, memory)
        server.stop()
        control.stop()
        output.close()
        account.close()
    return 0


def _begin_play(account: AccountSession, registry, agent, config, memory, memory_client: MemoryClient, memory_ready: bool) -> bool:
    if not account.logged_on:
        print("Log on with an available character before play.", file=sys.stderr)
        return False
    character = account.character
    knowledge = Bootstrapper(account.session, [item.character_name for item in registry.all()], character.name, memory=memory, replace_existing=config.telnet_replace_existing).bootstrap()
    memory.absorb_world(knowledge)
    _save_knowledge(config, account.auth_client, character.id, knowledge.to_document(character_id=character.id, character_name=character.name, agent_name=agent.name))
    if memory_ready:
        _save_memory(memory_client, agent.name, memory)
    room_name = knowledge.room.name if knowledge.room is not None else ""
    print("Knowledge: " f"{len(knowledge.help_topics)} help, " f"{len(knowledge.areas)} areas, " f"{len(knowledge.mobiles)} mobiles, " f"{len(knowledge.npcs)} npcs, " f"{len(knowledge.players)} players.")
    if room_name:
        print(f"Current room: {room_name}")
    return True


def _load_memory(client: MemoryClient, agent_name: str) -> tuple[WorkingMemory, bool]:
    memory = WorkingMemory()
    try:
        stored = client.load(agent_name)
    except (MemoryStoreError, ValueError) as exc:
        logger.warning("Working memory was not loaded: %s", exc)
        print(f"Working memory was not loaded: {exc}", file=sys.stderr)
        return memory, False
    if stored is None:
        return memory, True
    try:
        return WorkingMemory.from_collection(stored), True
    except (TypeError, ValueError) as exc:
        logger.warning("Working memory was not loaded: %s", exc)
        print(f"Working memory was not loaded: {exc}", file=sys.stderr)
        return memory, False


def _save_memory(client: MemoryClient, agent_name: str, memory: WorkingMemory) -> None:
    try:
        client.save(agent_name, memory.to_collection(agent_name))
    except (MemoryStoreError, ValueError) as exc:
        logger.warning("Working memory was not saved: %s", exc)
        print(f"Working memory was not saved: {exc}", file=sys.stderr)


def _save_knowledge(config: AgentConfig, auth_client: AuthClient, character_id: str, document: dict) -> None:
    headers = auth_client.get_auth_headers if auth_client is not None else (lambda: {})
    client = KnowledgeClient(config.api_base_url, path=config.knowledge_path, headers_provider=headers)
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
        list_agents(load_registry(config))
        return 0
    return run_agent(args.agent, config)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, LookupError, ValueError, FileNotFoundError, AgentStoreError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
