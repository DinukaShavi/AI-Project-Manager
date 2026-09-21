import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac_pdp import approver_roles_for_tool
from app.models.agent import ToolApproval
from app.models.tenant import User

# How long a pending approval stays actionable. Short enough that an unnoticed request
# cannot be approved days later against stale context, long enough for a real human to act.
APPROVAL_TTL_MINUTES = 30


class ToolApprovalService:
    """Real human-in-the-loop approval grants for high-risk tool calls (Phase 86).

    Before Phase 86, `ToolExecutor` accepted any non-empty `approval_token` string, so the
    approval gate could be bypassed by inventing one. Every grant issued here is instead:

      * a real secret (`secrets.token_urlsafe(32)`) stored only as a SHA-256 hash,
      * bound to one exact tool name + parameter fingerprint,
      * single-use (consumed on validation, so a captured token cannot be replayed),
      * scoped to the requesting organization, and
      * time-limited (`APPROVAL_TTL_MINUTES`).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def fingerprint_parameters(parameters: Optional[Dict[str, Any]]) -> str:
        """Stable SHA-256 over the parameters, so an approval granted for one call can never
        authorize a different one. Canonical form (sorted keys, no insignificant whitespace)
        means logically identical payloads fingerprint identically regardless of key order."""
        canonical = json.dumps(parameters or {}, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # ---------------------------------------------------------------- create

    async def create_pending(
        self,
        organization_id: UUID,
        tool_name: str,
        parameters: Dict[str, Any],
        requested_by_user_id: Optional[UUID] = None,
    ) -> ToolApproval:
        """Suspend a high-risk call by recording a real pending approval row."""
        record = ToolApproval(
            organization_id=organization_id,
            requested_by_user_id=requested_by_user_id,
            tool_name=tool_name,
            tool_parameters=parameters or {},
            parameters_fingerprint=self.fingerprint_parameters(parameters),
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=APPROVAL_TTL_MINUTES),
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)

        # M12 "WebSocket Events: Request tool approval alert" / spec section 5's Approval
        # Queuer ("publishes approval requests to user notification channels"). Reuses the
        # same ConnectionManager as the Phase 66 activity push rather than adding a second
        # real-time mechanism. Best-effort: a broadcast failure must never block the
        # suspension itself, which is the actual security control.
        try:
            from app.realtime.connection_manager import get_connection_manager

            await get_connection_manager().broadcast_to_organization(
                {
                    "event": "tool_approval_requested",
                    "payload": {
                        "approval_id": str(record.id),
                        "tool_name": record.tool_name,
                        "requested_by_user_id": str(requested_by_user_id) if requested_by_user_id else None,
                        "expires_at": record.expires_at.isoformat(),
                    },
                },
                organization_id,
            )
        except Exception as e:  # pragma: no cover - transport-level failure
            logger.warning(f"Tool approval: WebSocket alert failed for approval {record.id}: {e}")

        return record

    # ---------------------------------------------------------------- read

    async def list_pending(self, organization_id: UUID) -> List[ToolApproval]:
        """Pending, unexpired approvals for this organization -- the queue an approver's UI
        renders (M12: "UI widgets to review and approve pending tool calls")."""
        res = await self.session.execute(
            select(ToolApproval)
            .where(
                ToolApproval.organization_id == organization_id,
                ToolApproval.status == "pending",
                ToolApproval.expires_at > datetime.now(timezone.utc),
            )
            .order_by(ToolApproval.created_at.desc())
        )
        return list(res.scalars().all())

    async def _get_owned(self, approval_id: UUID, organization_id: UUID) -> Optional[ToolApproval]:
        """Fetch an approval only within the caller's own tenant. A record belonging to
        another organization is indistinguishable from a nonexistent one."""
        res = await self.session.execute(
            select(ToolApproval).where(
                ToolApproval.id == approval_id,
                ToolApproval.organization_id == organization_id,
            )
        )
        return res.scalar_one_or_none()

    # ---------------------------------------------------------------- decide

    async def approve(
        self,
        approval_id: UUID,
        approver: User,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Grant a pending approval, returning `(raw_token, None)` on success or
        `(None, reason)` on refusal. The raw token is returned exactly once and never
        stored -- only its hash is persisted."""
        record = await self._get_owned(approval_id, approver.organization_id)
        if record is None:
            return None, "Approval request not found."
        if record.status != "pending":
            return None, f"Approval request is already '{record.status}'."
        if record.expires_at <= datetime.now(timezone.utc):
            return None, "Approval request has expired."

        # Four-eyes: the person who requested a high-risk action may not sign off on it.
        # Without this a Developer still self-authorizes, just with an extra HTTP call.
        if record.requested_by_user_id is not None and record.requested_by_user_id == approver.id:
            return None, "The requester of a high-risk tool call may not approve their own request."

        allowed = {r.value for r in approver_roles_for_tool(record.tool_name)}
        approver_roles = {r.name for r in approver.roles}
        if not (approver_roles & allowed):
            return None, (
                f"Role(s) {sorted(approver_roles) or ['none']} may not approve "
                f"'{record.tool_name}'. Required: {sorted(allowed)}."
            )

        raw_token = secrets.token_urlsafe(32)
        record.approval_token_hash = self._hash_token(raw_token)
        record.approved_by_user_id = approver.id
        record.status = "approved"
        await self.session.commit()
        return raw_token, None

    async def reject(self, approval_id: UUID, approver: User) -> Tuple[bool, Optional[str]]:
        """Refuse a pending approval. Same authority rules as `approve`."""
        record = await self._get_owned(approval_id, approver.organization_id)
        if record is None:
            return False, "Approval request not found."
        if record.status != "pending":
            return False, f"Approval request is already '{record.status}'."

        allowed = {r.value for r in approver_roles_for_tool(record.tool_name)}
        if not ({r.name for r in approver.roles} & allowed):
            return False, f"Not authorized to decide approvals for '{record.tool_name}'."

        record.status = "rejected"
        record.approved_by_user_id = approver.id
        await self.session.commit()
        return True, None

    # ---------------------------------------------------------------- consume

    async def validate_and_consume(
        self,
        raw_token: str,
        organization_id: UUID,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Authorize exactly one execution of exactly this call.

        Every condition below is a real attack being closed, not defensive padding:
        an unknown hash rejects forged tokens; the org check blocks a grant issued in another
        tenant; the tool/fingerprint checks block replaying a benign approval against a
        different call; `status == "approved"` blocks using a pending or rejected row; the
        expiry check bounds the window; and flipping to `consumed` blocks replay.
        """
        if not raw_token:
            return False, "No approval token supplied."

        res = await self.session.execute(
            select(ToolApproval).where(
                ToolApproval.approval_token_hash == self._hash_token(raw_token)
            )
        )
        record = res.scalar_one_or_none()
        if record is None:
            return False, "Invalid approval token."

        if record.organization_id != organization_id:
            return False, "Approval token does not belong to this organization."
        if record.status != "approved":
            return False, f"Approval token is '{record.status}', not an active grant."
        if record.expires_at <= datetime.now(timezone.utc):
            return False, "Approval token has expired."
        if record.tool_name != tool_name:
            return False, "Approval token was issued for a different tool."
        if record.parameters_fingerprint != self.fingerprint_parameters(parameters):
            return False, "Approval token was issued for different parameters."

        record.status = "consumed"
        record.consumed_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True, None
