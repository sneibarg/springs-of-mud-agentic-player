"""Explicit gear evidence contracts. Display sightings never confirm ownership."""

from play.KmSyntax import frame, km_string, now_has, seq, token

_PIECE_TEXT = {"short": "som-short", "keyword": "som-keyword", "worn_slot": "som-worn-slot", "location": "som-location", "description": "som-description", "look_result": "som-look-result", "comparison": "som-comparison", "compared_to": "som-compared-to", "enchant": "som-enchant", "gear_kind": "som-gear-kind", "weapon_type": "som-weapon-type", "wield_band": "som-wield-band", "level_block": "som-level-block", "alignment_block": "som-alignment-block"}
_SOURCE_FLAGS = {"available": "som-gear-source-available", "permitted": "som-gear-source-permitted", "accessible": "som-gear-source-accessible", "loot_known": "som-gear-source-loot-known", "model_known": "som-gear-source-model-known"}


def boolean(value) -> str:
    if not isinstance(value, bool):
        raise ValueError("An observed flag must be true or false; null is unknown")
    return "t" if value else "f"


def number(value) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("An observed quantity must be a nonnegative integer")
    return str(value)


def required_text(data: dict, name: str) -> str:
    if not isinstance(data, dict):
        raise ValueError("An evidence row must be an object")
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing observed {name}")
    return value


def piece_forms(player: str, pieces: list[dict]) -> list[str]:
    forms = []
    for piece in pieces:
        identifier = required_text(piece, "item_id")
        allowed = {"item_id", "usable", "alignment_known", "object_level", "slot_index", "rejects"} | set(_PIECE_TEXT)
        if set(piece) - allowed:
            raise ValueError("Unsupported gear-piece fields: " + ", ".join(sorted(set(piece) - allowed)))
        pairs = [("instance-of", "Som-Gear-Piece")]
        for key, slot in _PIECE_TEXT.items():
            if key in piece:
                if not isinstance(piece[key], str):
                    raise ValueError(f"Invalid gear-piece {key}")
                pairs.append((slot, km_string(piece[key]) if key in {"short", "description", "compared_to"} else token(piece[key])))
        for key, slot in (("usable", "som-gear-usable"), ("alignment_known", "som-alignment-known")):
            if key in piece:
                pairs.append((slot, boolean(piece[key])))
        for key, slot in (("object_level", "som-object-level"), ("slot_index", "som-slot-index")):
            if key in piece:
                pairs.append((slot, number(piece[key])))
        if "rejects" in piece:
            if not isinstance(piece["rejects"], list) or any(side not in {"good", "evil", "neutral"} for side in piece["rejects"]):
                raise ValueError("Invalid rejected alignments")
            pairs.append(("som-rejects", seq(piece["rejects"])))
        forms.append(now_has(frame(player, "gear", identifier), pairs))
    return forms


def state_forms(player: str, observation_id: str, payload: dict) -> list[str]:
    allowed = {"state_id", "confirmed", "owned", "equipped", "coins", "room_id", "level", "alignment_side", "defeated"}
    if set(payload) - allowed:
        raise ValueError("Unsupported gear-state fields")
    if payload.get("confirmed") is not True:
        raise ValueError("A gear state must be explicitly confirmed")
    identifier = required_text(payload, "state_id")
    owned = payload.get("owned")
    equipped = payload.get("equipped")
    if not isinstance(owned, list) or not isinstance(equipped, list):
        raise ValueError("Complete owned and equipped sequences are required")
    forms = piece_forms(player, owned)
    identifiers = [piece["item_id"] for piece in owned]
    if len(set(identifiers)) != len(identifiers) or len(set(equipped)) != len(equipped) or any(identifier not in identifiers for identifier in equipped):
        raise ValueError("Equipped gear must reference unique owned identities")
    room = frame(player, "room", required_text(payload, "room_id"))
    pairs = [("instance-of", "Som-Gear-State"), ("som-gear-confirmed", "t"), ("som-gear-owned", seq(frame(player, "gear", identifier) for identifier in identifiers)), ("som-gear-equipped", seq(frame(player, "gear", identifier) for identifier in equipped)), ("som-gear-coins", number(payload.get("coins"))), ("som-gear-room", room), ("som-level", number(payload.get("level")))]
    if "alignment_side" in payload:
        if payload["alignment_side"] not in {"good", "evil", "neutral"}:
            raise ValueError("Invalid alignment side")
        pairs.append(("som-alignment-side", payload["alignment_side"]))
    if "defeated" in payload:
        if not isinstance(payload["defeated"], list):
            raise ValueError("Defeated encounters must be a sequence")
        pairs.append(("som-gear-defeated", seq(frame(player, "encounter", identifier) for identifier in payload["defeated"])))
    state = frame(player, "gear-state", observation_id + ":" + identifier)
    forms.extend([now_has(state, pairs), now_has("*" + player, [("som-gear-state", state)])])
    return forms


def source_forms(player: str, observation_id: str, payload: dict, sources: dict) -> list[str]:
    if set(payload) != {"sources"} or not isinstance(payload["sources"], list):
        raise ValueError("Gear opportunities require a sources list")
    forms = []
    for source in payload["sources"]:
        allowed = {"source_id", "kind", "item", "room_id", "holder_id", "price", "requires", "assessed_level", "risk", "yields"} | set(_SOURCE_FLAGS)
        if set(source) - allowed:
            raise ValueError("Unsupported gear-source fields")
        identifier = required_text(source, "source_id")
        kind = source.get("kind")
        if kind not in {"room", "shop", "corpse", "mobile", "player"}:
            raise ValueError("Invalid gear-source kind")
        item = source.get("item")
        if not isinstance(item, dict):
            raise ValueError("A gear source requires an observed item")
        forms.extend(piece_forms(player, [item]))
        room = frame(player, "room", required_text(source, "room_id"))
        holder_kind = "room" if kind == "room" else "encounter" if kind in {"mobile", "player", "shop"} else "corpse"
        holder = room if kind == "room" else frame(player, holder_kind, required_text(source, "holder_id"))
        pairs = [("instance-of", "Som-Gear-Source"), ("som-gear-source-kind", kind), ("som-gear-source-item", frame(player, "gear", item["item_id"])), ("som-gear-source-room", room), ("som-holder", holder)]
        for key, slot in _SOURCE_FLAGS.items():
            if key in source:
                pairs.append((slot, boolean(source[key])))
        for key, slot in (("price", "som-gear-source-price"), ("assessed_level", "som-gear-source-assessed-level")):
            if key in source:
                pairs.append((slot, number(source[key])))
        for key, slot in (("requires", "som-gear-source-requires"), ("yields", "som-gear-source-yields")):
            if key in source:
                if not isinstance(source[key], list):
                    raise ValueError(f"Gear-source {key} must be a sequence")
                if key == "yields" and item["item_id"] not in source[key]:
                    raise ValueError("A loot bundle must include its offered item")
                pairs.append((slot, seq(frame(player, "gear", item_id) for item_id in source[key])))
        if "risk" in source:
            if source["risk"] not in {"cautious", "steady", "bold"}:
                raise ValueError("Invalid assessed risk")
            pairs.append(("som-gear-source-risk", source["risk"]))
        subject = frame(player, "gear-source", observation_id + ":" + identifier)
        sources[identifier] = subject
        forms.append(now_has(subject, pairs))
    # This event is a complete ordered source snapshot, including explicit emptiness.
    identifiers = [source["source_id"] for source in payload["sources"]]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate gear-source identity")
    current = {identifier: sources[identifier] for identifier in identifiers}
    sources.clear()
    sources.update(current)
    forms.append(now_has("*" + player, [("som-known-gear-source", seq(sources.values()))]))
    return forms
