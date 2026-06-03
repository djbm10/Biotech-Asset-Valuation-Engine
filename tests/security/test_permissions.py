"""Tests for RBAC policy and audit log."""

import pytest
from datetime import datetime, timedelta

from bve.security.rbac import Permission, RBACPolicy, Role
from bve.security.audit_log import AuditLog, AuditEvent


class TestRBACPolicy:
    def setup_method(self):
        self.policy = RBACPolicy()

    def test_viewer_can_view_valuation(self):
        assert self.policy.has_permission(Role.VIEWER, Permission.VIEW_VALUATION)

    def test_viewer_cannot_edit_assumptions(self):
        assert not self.policy.has_permission(Role.VIEWER, Permission.EDIT_ASSUMPTIONS)

    def test_analyst_can_edit_assumptions(self):
        assert self.policy.has_permission(Role.ANALYST, Permission.EDIT_ASSUMPTIONS)

    def test_analyst_cannot_approve_assumptions(self):
        assert not self.policy.has_permission(Role.ANALYST, Permission.APPROVE_ASSUMPTIONS)

    def test_reviewer_can_approve_assumptions(self):
        assert self.policy.has_permission(Role.REVIEWER, Permission.APPROVE_ASSUMPTIONS)

    def test_reviewer_can_export_memo(self):
        assert self.policy.has_permission(Role.REVIEWER, Permission.EXPORT_MEMO)

    def test_admin_has_all_permissions(self):
        for perm in Permission:
            assert self.policy.has_permission(Role.ADMIN, perm), f"Admin missing {perm}"

    def test_external_read_only_only_view_valuation(self):
        allowed = self.policy.permissions_for(Role.EXTERNAL_READ_ONLY)
        assert "view_valuation" in allowed
        assert "edit_assumptions" not in allowed
        assert "export_memo" not in allowed

    def test_roles_with_permission_includes_admin(self):
        roles = self.policy.roles_with_permission(Permission.MANAGE_USERS)
        assert "admin" in roles

    def test_roles_with_permission_excludes_viewer(self):
        roles = self.policy.roles_with_permission(Permission.MANAGE_USERS)
        assert "viewer" not in roles

    def test_check_raises_for_unauthorized(self):
        with pytest.raises(PermissionError):
            self.policy.check(Role.VIEWER, Permission.EDIT_ASSUMPTIONS)

    def test_check_passes_for_authorized(self):
        # Should not raise
        self.policy.check(Role.ANALYST, Permission.EDIT_ASSUMPTIONS)

    def test_string_role_works(self):
        assert self.policy.has_permission("analyst", "edit_assumptions")

    def test_string_permission_works(self):
        assert self.policy.has_permission(Role.ANALYST, "edit_assumptions")

    def test_unknown_role_has_no_permissions(self):
        perms = self.policy.permissions_for("unknown_role")
        assert len(perms) == 0

    def test_has_permission_false_for_unknown_role(self):
        assert not self.policy.has_permission("unknown_role", Permission.VIEW_VALUATION)


class TestAuditLog:
    def setup_method(self):
        self.log = AuditLog()

    def test_record_creates_event(self):
        event = self.log.record("alice", "analyst", "view_valuation", resource_id="VKTX")
        assert event.event_id.startswith("evt-")
        assert event.user_id == "alice"

    def test_event_ids_are_sequential(self):
        e1 = self.log.record("alice", "analyst", "view_valuation")
        e2 = self.log.record("bob", "reviewer", "export_memo")
        assert e1.event_id != e2.event_id

    def test_query_by_user_id(self):
        self.log.record("alice", "analyst", "view_valuation")
        self.log.record("bob", "reviewer", "export_memo")
        results = self.log.query(user_id="alice")
        assert len(results) == 1
        assert results[0].user_id == "alice"

    def test_query_by_action(self):
        self.log.record("alice", "analyst", "view_valuation")
        self.log.record("alice", "analyst", "export_memo")
        results = self.log.query(action="export_memo")
        assert len(results) == 1

    def test_query_by_resource_id(self):
        self.log.record("alice", "analyst", "view_valuation", resource_id="VKTX")
        self.log.record("alice", "analyst", "view_valuation", resource_id="ALNY")
        results = self.log.query(resource_id="VKTX")
        assert len(results) == 1

    def test_query_by_since(self):
        self.log.record("alice", "analyst", "view_valuation")
        future = datetime.utcnow() + timedelta(hours=1)
        results = self.log.query(since=future)
        assert len(results) == 0

    def test_all_events(self):
        for _ in range(5):
            self.log.record("alice", "analyst", "view_valuation")
        assert len(self.log.all_events()) == 5

    def test_export_jsonl(self):
        self.log.record("alice", "analyst", "view_valuation")
        self.log.record("bob", "reviewer", "export_memo")
        jsonl = self.log.export_jsonl()
        lines = jsonl.strip().split("\n")
        assert len(lines) == 2
        import json
        parsed = json.loads(lines[0])
        assert "user_id" in parsed

    def test_record_detail_stored(self):
        event = self.log.record(
            "alice", "analyst", "edit_assumption",
            detail={"field": "peak_penetration", "old": 0.25, "new": 0.30}
        )
        assert event.detail["field"] == "peak_penetration"

    def test_failed_event_recorded(self):
        event = self.log.record("alice", "viewer", "export_memo", success=False)
        assert not event.success
