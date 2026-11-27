import re
from copy import deepcopy

from memory.CommandList import CommandList
from play.EvidenceMapping import EvidenceMapping
from play.KmGearEvidence import boolean, required_text, source_forms, state_forms
from play.KmSyntax import frame, km_string, now_has, player_frame, seq, token


class KmEvidenceAdapter:
    """Pure, player-scoped evidence plans. Submission and acknowledgments belong to handoff."""

    def __init__(self, player_name: str):
        self.player_name = player_frame(player_name)[1:]

    def plan(self, record, journal) -> EvidenceMapping:
        """Replay the immutable prefix so retries never read newer mutable session state."""
        if record.sequence < 1 or record.sequence > len(journal.records) or journal.records[record.sequence - 1] != record or record.observation_id != f"{journal.stream_id}:{record.sequence}":
            raise ValueError("Evidence must belong to the supplied ordered journal")
        state = {"commands": CommandList(), "available": None, "areas": {}, "rooms": {}, "mobiles": {}, "sources": {}}
        result = None
        prior = {}
        for item in journal.records[:record.sequence]:
            if item.observation_id != f"{journal.stream_id}:{item.sequence}" or item.sequence != len(prior) + 1 or any(identifier not in prior for identifier in item.source_ids):
                raise ValueError("Invalid evidence prefix or source reference")
            if item.kind == "model_enrichment" and item.transferable:
                expected = "help_index" if item.command == "categories" else "commands" if item.command == "commands" else "help" if item.command.startswith("help ") else "room"
                if item.source != "model" or not item.source_ids or any(prior[identifier].source != "server" or prior[identifier].kind != expected for identifier in item.source_ids):
                    raise ValueError("Model enrichment requires its matching server observation")
            result = self._plan(item, state)
            prior[item.observation_id] = item
        return result

    def _plan(self, record, state) -> EvidenceMapping:
        if not record.transferable:
            return self._result(record, (), (), local=True)
        payload = record.payload
        if not isinstance(payload, dict):
            return self._result(record, (), ("Evidence payload must be an object",))
        original = deepcopy(state)
        forms = []
        missing = []
        try:
            if record.kind == "commands":
                for command in CommandList.from_json(payload.get("commands", [])).records():
                    state["commands"].remember(command.name, category=command.category, help_text=command.help_text)
                names = payload["available"]
                if not isinstance(names, list):
                    raise ValueError("Command availability must be an ordered list")
                state["available"] = [command.name for command in CommandList.from_json([{"name": name} for name in names]).records()]
                for name in state["available"]:
                    state["commands"].remember(name)
                forms = self._commands(record, state)
            elif record.kind == "help":
                name = required_text(payload, "command")
                state["commands"].remember(name, help_text=payload.get("text", ""))
                forms = self._commands(record, state)
            elif record.kind == "model_enrichment":
                if not payload.get("applied"):
                    return self._result(record, (), ("unapplied model output",))
                if record.command in {"categories", "commands"} or record.command.startswith("help "):
                    for command in CommandList.from_json(payload["commands"]).records():
                        state["commands"].remember(command.name, category=command.category, help_text=command.help_text)
                    forms = self._commands(record, state)
                else:
                    missing.append("Room item enrichment does not establish gear ownership or an assessed opportunity")
            elif record.kind == "listed_areas":
                forms, missing = self._areas(record, state)
            elif record.kind in {"room", "consider", "observation", "score"}:
                forms, missing = self._world(record, state)
                if record.kind == "score":
                    missing.append("Score/progress projection belongs to the inference request contract")
                elif record.kind == "observation" and (payload.get("combat") or payload.get("progress")):
                    missing.append("Combat/progress state is not a historical mobile fact")
            elif record.kind == "gear_state":
                if record.source != "server":
                    raise ValueError("Model output cannot confirm a gear state")
                if payload.get("room_id") not in state["rooms"]:
                    raise ValueError("Gear state requires an observed explored room")
                forms = state_forms(self.player_name, record.observation_id, payload)
            elif record.kind == "gear_sources":
                if record.source != "server":
                    raise ValueError("Gear opportunities require explicit observation evidence")
                if not isinstance(payload.get("sources"), list) or any(not isinstance(source, dict) for source in payload["sources"]):
                    raise ValueError("Gear sources must be objects in a complete sequence")
                if any(source.get("room_id") not in state["rooms"] for source in payload["sources"]):
                    raise ValueError("Gear sources require observed explored rooms")
                forms = source_forms(self.player_name, record.observation_id, payload, state["sources"])
            else:
                missing.append(f"No KM mapping for {record.kind}")
        except (KeyError, TypeError, ValueError) as exc:
            # A malformed record cannot yield a submit-ready partial list of expressions.
            state.clear()
            state.update(original)
            return self._result(record, (), (str(exc),))
        return self._result(record, forms, missing)

    def _result(self, record, forms, missing, *, local: bool = False) -> EvidenceMapping:
        status = "local" if local else "partial" if missing and forms else "unsupported" if missing else "mapped" if forms else "unsupported"
        return EvidenceMapping(record.observation_id, self.player_name, status, tuple(forms), tuple(missing) or (() if forms or local else ("No supported facts in this observation",)))

    def _commands(self, record, state) -> list[str]:
        forms = []
        rows = {}
        for command in state["commands"].records():
            subject = frame(self.player_name, "command", record.observation_id + ":" + command.name)
            rows[command.name] = subject
            pairs = [("instance-of", "Som-Known-Command"), ("som-command-name", token(command.name))]
            if command.category:
                pairs.append(("som-command-category", token(command.category.lower())))
            if command.help_text:
                pairs.append(("som-command-help", km_string(command.help_text)))
            forms.append(now_has(subject, pairs))
        if state["available"] is not None:
            forms.append(now_has(player_frame(self.player_name), [("som-known-command", seq(rows[name] for name in state["available"]))]))
        return forms

    def _areas(self, record, state) -> tuple[list[str], list[str]]:
        forms = []
        missing = []
        current = {}
        for area in record.payload["areas"]:
            name = required_text(area, "name")
            subject = frame(self.player_name, "area", record.observation_id + ":" + name.strip().lower())
            current[name.strip().lower()] = subject
            pairs = [("instance-of", "Som-Area"), ("som-area-name", km_string(name))]
            if area.get("author"):
                if not isinstance(area["author"], str):
                    raise ValueError("An area author must be text")
                pairs.append(("som-area-author", km_string(area["author"])))
            levels = area.get("level_range", "")
            match = re.fullmatch(r"\s*(\d+)\s*[-–]\s*(\d+)\s*", levels) if levels else None
            if match:
                low, high = map(int, match.groups())
                if low > high:
                    raise ValueError("Area level range is reversed")
                pairs.extend([("som-level-low", str(low)), ("som-level-high", str(high))])
            elif levels:
                missing.append(f"Unmapped area level range: {levels}")
            # Listing an area never asserts som-explored, including on later refresh.
            forms.append(now_has(subject, pairs))
        state["areas"] = current
        forms.append(now_has(player_frame(self.player_name), [("som-area", seq(current.values()))]))
        return forms, missing

    def _world(self, record, state) -> tuple[list[str], list[str]]:
        payload = record.payload
        forms = []
        missing = []
        rooms = []
        for room in payload.get("room_updates", []):
            if room.get("room_id") not in state["rooms"]:
                missing.append("Historical snapshots cannot establish an explored room")
            else:
                rooms.append(room)
        if record.kind == "room":
            if not payload.get("complete") or payload.get("room") is None:
                return [], ["Incomplete room observation"]
            rooms.append(payload["room"])
        for room in rooms:
            identifier = required_text(room, "room_id")
            if record.kind != "room" and identifier not in state["rooms"]:
                missing.append("Historical snapshots cannot establish an explored room")
                continue
            state["rooms"][identifier] = room
        # Rebuild indexed map facts from the prefix, including changed forward edges.
        if rooms:
            for identifier, room in state["rooms"].items():
                room_subject = frame(self.player_name, "room", identifier)
                exits = []
                for entry in room.get("exit_records", []):
                    if not entry.get("active", True):
                        continue
                    subject = frame(self.player_name, "exit", record.observation_id + ":" + required_text(entry, "exit_id"))
                    exits.append(subject)
                    pairs = [("instance-of", "Som-Room-Exit"), ("som-exit-direction", token(required_text(entry, "direction")))]
                    assessed = all(isinstance(entry.get(key), bool) for key in ("requires_open", "requires_unlock"))
                    for key, slot in (("requires_open", "som-requires-open"), ("requires_unlock", "som-requires-unlock")):
                        if entry.get(key) is not None:
                            pairs.append((slot, boolean(entry[key])))
                    destination = entry.get("destination_id")
                    if destination in state["rooms"] and assessed:
                        pairs.append(("som-exit-to", frame(self.player_name, "room", destination)))
                    elif destination:
                        missing.append(f"Exit {entry['exit_id']} destination withheld until room and door prerequisites are assessed")
                    forms.append(now_has(subject, pairs))
                forms.append(now_has(room_subject, [("instance-of", "Som-Explored-Room"), ("som-place-name", km_string(required_text(room, "name"))), ("som-room-exit", seq(exits))]))
            forms.append(now_has(player_frame(self.player_name), [("som-explored-room", seq(frame(self.player_name, "room", identifier) for identifier in state["rooms"]))]))
        beings = payload.get("beings", [])
        for being in beings:
            identifier = required_text(being, "being_id")
            kind = being.get("kind")
            if kind not in {"mobile", "npc", "player"}:
                missing.append(f"Unknown being classification: {identifier}")
                continue
            subject = frame(self.player_name, "encounter", identifier)
            state["mobiles"][identifier] = subject
            pairs = [("instance-of", "Som-Mobile"), ("som-mobile-name", km_string(required_text(being, "name"))), ("som-player", boolean(kind == "player"))]
            if being.get("room_id") in state["rooms"]:
                pairs.append(("som-mobile-last-room", frame(self.player_name, "room", being["room_id"])))
            if being.get("aggressive") is not None:
                pairs.append(("som-aggressive", boolean(being["aggressive"])))
            forms.append(now_has(subject, pairs))
        if beings or record.kind == "room":
            forms.append(now_has(player_frame(self.player_name), [("som-known-mobile", seq(state["mobiles"].values()))]))
        visit = payload.get("visit", {})
        if "beings" in payload:
            readings = []
            for being in beings if visit.get("current") else []:
                if being.get("kind") not in {"mobile", "npc", "player"}:
                    continue
                identifier = being["being_id"]
                subject = frame(self.player_name, "reading", record.observation_id + ":" + identifier)
                readings.append(subject)
                outlook = payload.get("fresh_considers", {}).get(identifier)
                fresh = identifier in visit.get("fresh", []) and outlook in {"safe", "even", "risky", "fatal"}
                pairs = [("instance-of", "Som-Mobile-Reading"), ("som-mobile-name", km_string(being["name"])), ("som-player", boolean(being["kind"] == "player")), ("som-fresh", boolean(fresh))]
                if fresh:
                    pairs.append(("som-outlook", token(outlook)))
                forms.append(now_has(subject, pairs))
            projection = frame(self.player_name, "reading-view", record.observation_id)
            forms.append(now_has(projection, [("instance-of", "Som-Goal-View"), ("som-reading", seq(readings))]))
        if record.kind == "consider" and "beings" not in payload:
            missing.append("Consider evidence lacks its captured tactical context")
        return forms, missing
