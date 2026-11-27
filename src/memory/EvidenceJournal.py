import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from memory.SessionEvidence import SessionEvidence
from util.SharedUtil import SharedUtil


@dataclass
class EvidenceJournal:
    """Ordered local handoff queue. Collection and snapshot saving never acknowledge it."""

    stream_id: str = ""
    records: list[SessionEvidence] = field(default_factory=list)
    accepted_ids: set[str] = field(default_factory=set)

    def append(self, kind: str, *, origin: str, source: str = "server", command: str = "", lines=(), source_ids=(), payload: dict | None = None, transferable: bool = False) -> SessionEvidence:
        source_ids = tuple(source_ids)
        known = {record.observation_id for record in self.records}
        if any(identifier not in known for identifier in source_ids):
            raise ValueError("Evidence source must belong to this journal")
        payload_json = json.dumps(payload or {})
        if not self.stream_id:
            self.stream_id = uuid4().hex
        sequence = len(self.records) + 1
        record = SessionEvidence(f"{self.stream_id}:{sequence}", sequence, datetime.now(timezone.utc).isoformat(), kind, origin, source, command, tuple(lines), source_ids, payload_json, transferable)
        self.records.append(record)
        return record

    def pending(self) -> list[SessionEvidence]:
        return [record for record in self.records if record.transferable and record.observation_id not in self.accepted_ids]

    def acknowledge(self, identifiers) -> None:
        """Called only after every required mapping for these records has succeeded."""
        selected = set(identifiers)
        if not selected <= {record.observation_id for record in self.records if record.transferable}:
            raise ValueError("Cannot acknowledge local-only evidence or evidence from another journal")
        self.accepted_ids.update(selected)

    def to_review(self) -> dict:
        return {"stream_id": self.stream_id, "records": [record.to_review() for record in self.records], "accepted_ids": sorted(self.accepted_ids)}

    @classmethod
    def from_json(cls, data: dict) -> "EvidenceJournal":
        data = SharedUtil.snake_tree(data)
        journal = cls(stream_id=data.get("stream_id", ""), records=[SessionEvidence.from_json(record) for record in data.get("records", [])])
        if any(record.sequence != index or record.observation_id != f"{journal.stream_id}:{index}" for index, record in enumerate(journal.records, 1)):
            raise ValueError("Invalid evidence ordering or stream identity")
        journal.acknowledge(data.get("accepted_ids", []))
        return journal
