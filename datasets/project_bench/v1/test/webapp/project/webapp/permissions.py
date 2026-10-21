"""Roles, the permissions each role grants, and who may manage which account."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.VIEWER: frozenset({"profile:read"}),
    Role.EDITOR: frozenset({"profile:read", "post:write"}),
    Role.ADMIN: frozenset({"profile:read", "post:write", "user:manage"}),
}


class PermissionDenied(Exception):
    """Raised when an action needs a permission the caller's role lacks."""

    def __init__(self, permission: str) -> None:
        super().__init__(f"missing permission: {permission}")
        self.permission = permission


def parse_role(value: str) -> Role:
    """Turn "Admin", " editor " and the like into a Role; ValueError if unknown."""
    return Role(value.strip().lower())


def has_permission(role: Role, permission: str) -> bool:
    """True when the role grants the permission."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require(role: Role, permission: str) -> None:
    """Raise PermissionDenied unless the role grants the permission."""
    if not has_permission(role, permission):
        raise PermissionDenied(permission)


def can_manage_user(actor: str, actor_role: Role, target: str) -> bool:
    """Anyone may manage their own account; another's needs "user:manage"."""
    return actor == target or has_permission(actor_role, "user:manage")
