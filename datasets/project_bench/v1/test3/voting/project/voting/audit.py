"""A tamper-evident audit log of everything that happens during an election.

Each entry carries the SHA-256 hash of the previous entry, so changing or removing an
entry breaks the chain from that point on. The log never records which candidates a
member voted for.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    """One event in the log."""

    seq: int
    at: datetime
    event: str
    detail: dict[str, str]
    prev_hash: str
    hash: str


def entry_hash(seq: int, at: datetime, event: str, detail: dict[str, str], prev: str) -> str:
    """Return the hash that seals an entry's contents to the previous entry."""
    payload = json.dumps(
        {"seq": seq, "at": at.isoformat(), "event": event, "detail": detail, "prev": prev},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class AuditLog:
    """Append-only list of audit entries."""

    entries: list[AuditEntry] = field(default_factory=list)

    def record(self, event: str, at: datetime, **detail: str) -> AuditEntry:
        """Append an event and return the sealed entry."""
        seq = len(self.entries) + 1
        prev = self.entries[-1].hash if self.entries else GENESIS
        sealed = entry_hash(seq, at, event, dict(detail), prev)
        entry = AuditEntry(seq, at, event, dict(detail), prev, sealed)
        self.entries.append(entry)
        return entry

    def verify(self) -> bool:
        """Return True when no entry has been changed, removed or reordered."""
        prev = GENESIS
        for seq, entry in enumerate(self.entries, start=1):
            expected = entry_hash(seq, entry.at, entry.event, entry.detail, prev)
            if entry.seq != seq or entry.prev_hash != prev or entry.hash != expected:
                return False
            prev = entry.hash
        return True


def suspicious_activity(entries: list[AuditEntry], max_rejections: int) -> list[str]:
    """Return warnings for an election official reading the log.

    A warning is raised for a member issued more than one token, for a token used to
    cast more than one ballot, and for a token whose ballots were rejected more than
    ``max_rejections`` times. Each problem is reported once, in log order.
    """
    warnings: list[str] = []
    issued: set[str] = set()
    cast: set[str] = set()
    rejections: dict[str, int] = {}
    for entry in entries:
        if entry.event == "token_issued":
            member = entry.detail.get("member_id", "")
            if member in issued:
                warnings.append(f"#{entry.seq}: {member} was issued a second token")
            issued.add(member)
        elif entry.event in ("ballot_cast", "ballot_rejected"):
            token_ref = entry.detail.get("token_ref", "")
            if token_ref:
                if entry.event == "ballot_cast":
                    if token_ref in cast:
                        warnings.append(f"#{entry.seq}: token {token_ref} voted twice")
                    cast.add(token_ref)
                else:
                    rejections[token_ref] = rejections.get(token_ref, 0) + 1
                    if rejections[token_ref] == max_rejections + 1:
                        warnings.append(
                            f"#{entry.seq}: token {token_ref} rejected "
                            f"{rejections[token_ref]} times"
                        )
    return warnings
