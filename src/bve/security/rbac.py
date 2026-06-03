"""Role-based access control."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml


class Permission(str, Enum):
    VIEW_VALUATION = "view_valuation"
    VIEW_WATCHLIST = "view_watchlist"
    EDIT_ASSUMPTIONS = "edit_assumptions"
    APPROVE_ASSUMPTIONS = "approve_assumptions"
    RUN_CALIBRATION = "run_calibration"
    EXPORT_MEMO = "export_memo"
    VIEW_PROPRIETARY_ACQUIRER_PROFILES = "view_proprietary_acquirer_profiles"
    VIEW_TRADE_RECOMMENDATIONS = "view_trade_recommendations"
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT_LOG = "view_audit_log"


class Role(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    ADMIN = "admin"
    EXTERNAL_READ_ONLY = "external_read_only"


class RBACPolicy:
    """Loads role permissions from YAML and enforces access control."""

    def __init__(self, permissions_path: str | Path | None = None) -> None:
        if permissions_path is None:
            permissions_path = Path(__file__).parent / "permissions.yaml"
        self._path = Path(permissions_path)
        self._role_permissions: dict[str, set[str]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with open(self._path) as f:
            raw = yaml.safe_load(f)
        for role_name, spec in raw.get("roles", {}).items():
            self._role_permissions[role_name] = set(spec.get("permissions", []))

    def has_permission(self, role: str | Role, permission: str | Permission) -> bool:
        role_str = role.value if isinstance(role, Role) else role
        perm_str = permission.value if isinstance(permission, Permission) else permission
        return perm_str in self._role_permissions.get(role_str, set())

    def permissions_for(self, role: str | Role) -> set[str]:
        role_str = role.value if isinstance(role, Role) else role
        return frozenset(self._role_permissions.get(role_str, set()))

    def roles_with_permission(self, permission: str | Permission) -> list[str]:
        perm_str = permission.value if isinstance(permission, Permission) else permission
        return [role for role, perms in self._role_permissions.items() if perm_str in perms]

    def check(self, role: str | Role, permission: str | Permission) -> None:
        """Raise PermissionError if role does not have permission."""
        if not self.has_permission(role, permission):
            role_str = role.value if isinstance(role, Role) else role
            perm_str = permission.value if isinstance(permission, Permission) else permission
            raise PermissionError(f"Role '{role_str}' does not have permission '{perm_str}'")
