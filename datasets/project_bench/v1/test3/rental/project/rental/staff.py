"""Counter staff of the agency's branches."""

from __future__ import annotations

from dataclasses import dataclass

ROLES = frozenset({"agent", "manager"})


@dataclass(frozen=True)
class Staff:
    """A person working the counter at one branch, as an ``agent`` or a ``manager``."""

    name: str
    role: str
    branch_code: str

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"unknown role: {self.role!r}")

    @property
    def is_manager(self) -> bool:
        """True for branch managers."""
        return self.role == "manager"
