"""AgentPermissionManager: role + ownership + share-scope checks. Runs before every tool handler.

The model never decides permissions. A tool is allowed only if:
  1. the caller's role is in the tool's `roles`,
  2. the role is granted the tool's permission string,
  3. for doctors, an ACTIVE CareLink to the patient exists (re-checked on every call, so a revoke bites at once),
  4. the share scope (full / labs / medicines) covers the data the tool reads.
"""
from __future__ import annotations

from sqlalchemy import select

from ..models import CareLink
from .context import AgentContext
from .types import ToolSpec

PATIENT_PERMS = {
    "records:read", "records:write", "meds:read", "health:read", "careloop:read", "careloop:write",
    "doctors:read", "sharing:read", "sharing:write", "nav:use", "pdf:create", "profile:read",
}
DOCTOR_PERMS = {"records:read", "meds:read", "health:read", "careloop:read", "nav:use", "pdf:create", "consult:draft"}

ROLE_PERMS = {"patient": PATIENT_PERMS, "doctor": DOCTOR_PERMS}

# Permission -> share scopes that may use it. "full" covers everything.
SCOPE_ALLOWS = {
    "full": None,
    "labs": {"records:read", "health:read", "nav:use"},
    "medicines": {"meds:read", "records:read", "nav:use"},
}
# Document types visible per scope (mirrors /api/shares/{token}/snapshot).
SCOPE_DOC_TYPES = {"full": None, "labs": {"lab"}, "medicines": {"prescription"}}


class AgentPermissionManager:
    def check(self, ctx: AgentContext, spec: ToolSpec) -> tuple[bool, str | None]:
        if ctx.role not in spec.roles:
            return False, "This tool is not available to your account type."
        if spec.permission not in ROLE_PERMS.get(ctx.role, set()):
            return False, "You do not have permission for this action."
        allowed = SCOPE_ALLOWS.get(ctx.scope)
        if ctx.scope not in SCOPE_ALLOWS:
            return False, "Unknown access scope."
        if allowed is not None and spec.permission not in allowed:
            return False, "This share does not include that information."
        if ctx.role == "doctor" and not self._linked(ctx):
            return False, "No active link to this patient."
        if ctx.role == "patient" and ctx.actor_id != ctx.patient_id:
            return False, "A patient agent can only work on its own record."
        return True, None

    @staticmethod
    def _linked(ctx: AgentContext) -> bool:
        link = ctx.db.scalar(select(CareLink).where(
            CareLink.patient_id == ctx.patient_id, CareLink.doctor_user_id == ctx.actor_id, CareLink.status == "active"))
        return link is not None

    @staticmethod
    def doc_types(ctx: AgentContext) -> set[str] | None:
        """Document types this caller may see, or None for all."""
        return SCOPE_DOC_TYPES.get(ctx.scope)
