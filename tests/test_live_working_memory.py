import json
import os
import re
import sys
import unittest
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent.AgentCollection import AgentCollection
from memory.WorkingMemory import WorkingMemory
from play.WorldKnowledge import WorldKnowledge
from play.WorldReader import parse_room, parse_who
from tests.live_session import QUIT_PHRASE, LivePlay, require_live_play


_ARTICLES = {"a", "an", "the", "some"}
_OUTLOOKS = {"safe", "even", "risky", "fatal"}
_REVERSE = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "down",
    "down": "up",
}
_CLOSED_DOOR = re.compile(r"^the .+ is closed\.$", re.IGNORECASE)
_MOVE_LIMIT = 5
_OUTPUT = Path(__file__).resolve().parent / "output"
_AGENTS = Path(__file__).resolve().parents[1] / "resources" / "collections" / "SOMDB.Agents.json"


class TestLiveWorkingMemory(unittest.TestCase):
    def setUp(self):
        _OUTPUT.mkdir(parents=True, exist_ok=True)
        self.review_path = _OUTPUT / f"{self._testMethodName}.json"
        if self.review_path.is_file():
            self.review_path.unlink()

    def test_live_working_memory_mobiles(self):
        play = require_live_play(self)
        try:
            players = parse_who(play.exchange("who"), set(), play.character.name)
            _stand(play)
            observation = _find_mobile(play, players)
            mobile = observation.mobiles[0]

            knowledge = WorldKnowledge()
            for player in players:
                knowledge.remember_player(player)
            knowledge.room = observation.room
            for being in observation.mobiles:
                knowledge.remember_mobile(being)
            for being in observation.npcs:
                knowledge.remember_npc(being)
            for player in observation.players_present:
                knowledge.note_player_seen(player.name, observation.room.name)

            memory = WorkingMemory()
            memory.absorb_world(knowledge)
            stored = memory.being_named(mobile.name)
            self.assertIsNotNone(stored)
            self.assertEqual(stored.kind, "mobile")
            self.assertEqual(stored.room_name, observation.room.name)
            self.assertEqual(stored.auras, mobile.auras)
            self.assertEqual(stored.auras, ["White Aura"])
            self.assertIsNone(memory.being_named(play.character.name))
            for being in observation.npcs:
                self.assertEqual(memory.being_named(being.name).auras, being.auras)
            for player in observation.players_present:
                if player.self_character:
                    continue
                remembered = memory.being_named(player.name)
                self.assertIsNotNone(remembered)
                self.assertEqual(remembered.kind, "player")
                self.assertEqual(remembered.auras, player.auras)

            keyword = _consider_keyword(mobile.name)
            reading = memory.remember_consider(
                keyword,
                play.exchange(f"consider {keyword}"),
                kind="mobile",
            )
            self.assertTrue(reading.estimated, reading.text)
            self.assertIn(reading.outlook, _OUTLOOKS)
            self.assertIs(memory.consider_for(keyword), reading)
            self.assertEqual(memory.being_named(mobile.name).auras, ["White Aura"])
            self._dump(memory)
            review = json.loads(self.review_path.read_text(encoding="utf-8"))
            dumped = next(item for item in review["mobiles"] if item["name"] == mobile.name)
            self.assertEqual(dumped["auras"], ["White Aura"])
            for being in observation.npcs:
                dumped_npc = next(item for item in review["npcs"] if item["name"] == being.name)
                self.assertEqual(dumped_npc["auras"], being.auras)
            for player in observation.players_present:
                if player.self_character:
                    continue
                dumped_player = next(
                    item for item in review["players"] + review["agentic_players"] if item["name"] == player.name
                )
                self.assertEqual(dumped_player["auras"], player.auras)

            farewell = play.quit()
            self.assertTrue(any(QUIT_PHRASE in line for line in farewell))
        finally:
            play.close()

    def test_live_working_memory_players(self):
        play = require_live_play(self)
        try:
            players = parse_who(play.exchange("who"), _agent_character_names(), play.character.name)
            _stand(play)
            observation = _find_player(play, players)
            other = _other_players(observation, play.character.name)[0]

            knowledge = WorldKnowledge()
            for player in players:
                knowledge.remember_player(player)
            knowledge.room = observation.room
            for being in observation.mobiles:
                knowledge.remember_mobile(being)
            for being in observation.npcs:
                knowledge.remember_npc(being)
            for player in observation.players_present:
                knowledge.note_player_seen(player.name, observation.room.name)

            memory = WorkingMemory()
            memory.absorb_world(knowledge)
            stored = memory.being_named(other.name)
            self.assertIsNotNone(stored)
            self.assertEqual(stored.kind, "player")
            self.assertEqual(stored.agentic, other.agentic)
            self.assertEqual(stored.room_name, observation.room.name)
            self.assertEqual(stored.auras, other.auras)
            self.assertIsNone(memory.being_named(play.character.name))
            room = memory.room_named(observation.room.name)
            self.assertIsNotNone(room)
            self.assertEqual(room.description, observation.room.description)
            self.assertEqual(room.exits, observation.room.exits)
            group = memory.agentic_players() if other.agentic else memory.players()
            self.assertIn(stored, group)
            for being in observation.mobiles:
                self.assertEqual(memory.being_named(being.name).auras, being.auras)
            for being in observation.npcs:
                self.assertEqual(memory.being_named(being.name).auras, being.auras)

            reading = memory.remember_consider(
                other.name,
                play.exchange(f"consider {other.name}"),
                kind="player",
                agentic=other.agentic,
            )
            self.assertEqual(reading.kind, "agentic" if other.agentic else "player")
            self.assertTrue(reading.estimated, reading.text)
            self.assertIn(reading.outlook, _OUTLOOKS)
            self.assertIs(memory.consider_for(other.name), reading)
            self.assertEqual(memory.being_named(other.name).auras, other.auras)
            self.assertEqual(memory.being_named(other.name).room_name, observation.room.name)
            self._dump(memory)
            review = json.loads(self.review_path.read_text(encoding="utf-8"))
            listed = review["agentic_players"] if other.agentic else review["players"]
            dumped = next(item for item in listed if item["name"] == other.name)
            self.assertEqual(dumped["kind"], "player")
            self.assertEqual(dumped["agentic"], other.agentic)
            self.assertEqual(dumped["room_name"], observation.room.name)
            self.assertEqual(dumped["auras"], other.auras)
            dumped_room = next(item for item in review["rooms"] if item["name"] == observation.room.name)
            self.assertEqual(dumped_room["description"], observation.room.description)
            self.assertEqual(dumped_room["exits"], observation.room.exits)
            dumped_consider = next(item for item in review["considers"] if item["target"] == other.name)
            self.assertEqual(dumped_consider["outlook"], reading.outlook)
            self.assertEqual(dumped_consider["kind"], reading.kind)
            for being in observation.mobiles:
                dumped_mobile = next(item for item in review["mobiles"] if item["name"] == being.name)
                self.assertEqual(dumped_mobile["auras"], being.auras)
            for being in observation.npcs:
                dumped_npc = next(item for item in review["npcs"] if item["name"] == being.name)
                self.assertEqual(dumped_npc["auras"], being.auras)

            farewell = play.quit()
            self.assertTrue(any(QUIT_PHRASE in line for line in farewell))
        finally:
            play.close()

    def test_live_working_memory_rooms(self):
        play = require_live_play(self)
        try:
            _stand(play)
            first = _read_room(play, [])
            self.assertTrue(first.room.name)
            self.assertTrue(first.room.description.strip())
            self.assertTrue(first.room.exits)

            memory = WorkingMemory()
            _absorb_room(memory, first)
            second = _enter_other_room(play, first.room.name, first.room.exits)
            self.assertNotEqual(second.room.name.lower(), first.room.name.lower())
            self.assertTrue(second.room.description.strip())
            self.assertTrue(second.room.exits)
            _absorb_room(memory, second)

            self.assertEqual(len(memory.rooms()), 2)
            for observation in (first, second):
                stored = memory.room_named(observation.room.name)
                self.assertIsNotNone(stored)
                self.assertEqual(stored.description, observation.room.description)
                self.assertEqual(stored.exits, observation.room.exits)
            self._dump(memory)

            farewell = play.quit()
            self.assertTrue(any(QUIT_PHRASE in line for line in farewell))
        finally:
            play.close()


    def _dump(self, memory: WorkingMemory) -> None:
        written = Path(memory.write_review(str(self.review_path)))
        self.assertEqual(written, self.review_path)
        self.assertTrue(self.review_path.is_file())
        self.assertGreater(self.review_path.stat().st_size, 0)


def _absorb_room(memory: WorkingMemory, observation) -> None:
    knowledge = WorldKnowledge()
    knowledge.room = observation.room
    memory.absorb_world(knowledge)


def _read_room(play: LivePlay, players: list):
    look = play.exchange("look")
    if not any(line.strip().lower().startswith("obvious exits") for line in look):
        look = look + play.exchange("exits")
    return parse_room(look, players)


def _stand(play: LivePlay) -> None:
    play.exchange("stand")


def _agent_character_names() -> set[str]:
    collection = AgentCollection.load(_AGENTS)
    return {agent.character_name for agent in collection.agents if agent.character_name}


def _other_players(observation, self_name: str) -> list:
    self_key = self_name.strip().lower()
    return [
        player for player in observation.players_present
        if not player.self_character and player.name.strip().lower() != self_key
    ]


def _find_player(play: LivePlay, players: list):
    observation = _read_room(play, players)
    came_from = None
    seen = [observation.room.name or "(unnamed)"]
    for step in range(_MOVE_LIMIT + 1):
        if _other_players(observation, play.character.name):
            return observation
        if step == _MOVE_LIMIT:
            break
        moved = False
        for direction in _ordered_exits(observation.room.exits, came_from):
            lines = play.exchange(direction)
            if _move_failed(lines):
                continue
            nxt = _read_room(play, players)
            if not nxt.room.name or nxt.room.name.lower() == observation.room.name.lower():
                continue
            came_from = _REVERSE.get(direction)
            observation = nxt
            seen.append(observation.room.name)
            moved = True
            break
        if not moved:
            break
    visible = ", ".join(player.name for player in players if not player.self_character) or "(none)"
    raise AssertionError(f"No other player found. Who: {visible}. Rooms: {', '.join(seen)}")


def _find_mobile(play: LivePlay, players: list):
    observation = _read_room(play, players)
    came_from = None
    seen = [observation.room.name or "(unnamed)"]
    for step in range(_MOVE_LIMIT + 1):
        if observation.mobiles:
            return observation
        if step == _MOVE_LIMIT:
            break
        moved = False
        for direction in _ordered_exits(observation.room.exits, came_from):
            lines = play.exchange(direction)
            if _move_failed(lines):
                continue
            nxt = _read_room(play, players)
            if not nxt.room.name or nxt.room.name.lower() == observation.room.name.lower():
                continue
            came_from = _REVERSE.get(direction)
            observation = nxt
            seen.append(observation.room.name)
            moved = True
            break
        if not moved:
            break
    raise AssertionError("No mobile found. Rooms: " + ", ".join(seen))


def _enter_other_room(play: LivePlay, room_name: str, exits: list[str]):
    for direction in exits:
        lines = play.exchange(direction)
        if _move_failed(lines):
            continue
        candidate = _read_room(play, [])
        if candidate.room.name and candidate.room.name.lower() != room_name.lower():
            return candidate
        break
    raise AssertionError(f"No open exit left {room_name}.")


def _ordered_exits(exits: list[str], came_from: str | None) -> list[str]:
    if came_from not in exits:
        return list(exits)
    return [direction for direction in exits if direction != came_from] + [came_from]


def _move_failed(lines: list[str]) -> bool:
    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()
        if "you feel too relaxed" in lowered:
            return True
        if lowered.startswith("you can't go that direction"):
            return True
        if lowered.startswith("alas, you cannot go"):
            return True
        if _CLOSED_DOOR.match(stripped):
            return True
    return False


def _consider_keyword(display_name: str) -> str:
    tokens = [token for token in display_name.split() if token.lower() not in _ARTICLES]
    if not tokens:
        raise AssertionError(f"No consider keyword in {display_name!r}.")
    return tokens[-1]


if __name__ == "__main__":
    unittest.main()
