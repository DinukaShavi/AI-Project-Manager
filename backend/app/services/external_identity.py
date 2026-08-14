from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.external_identity import ExternalIdentity
from app.models.tenant import User
from app.core.rbac_pdp import ADMIN_ROLES
from app.services.audit import AuditService


class ExternalIdentityService:
    def __init__(self, session: AsyncSession):
        """Maps an AI-TPM User to their real account on a connected external provider
        (backend/app/models/external_identity.py). This is the foundation Jira/GitHub/Slack/
        Google user-mapping, "who's overloaded", "who owns this PR", and calendar attendee
        resolution all depend on -- it does not itself implement any of those features."""
        self.session = session
        self.audit_service = AuditService(session)

    async def get_identity_for_user(self, organization_id: UUID, user_id: UUID, provider: str) -> Optional[ExternalIdentity]:
        """Fetch the caller's own active identity for a provider, tenant-scoped."""
        res = await self.session.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.organization_id == organization_id,
                ExternalIdentity.user_id == user_id,
                ExternalIdentity.provider == provider,
                ExternalIdentity.is_active == True,
            )
        )
        return res.scalar_one_or_none()

    async def list_identities_for_user(self, organization_id: UUID, user_id: UUID) -> List[ExternalIdentity]:
        """List all of the caller's own active identities across every provider, for the
        Settings "Connected Accounts" panel."""
        res = await self.session.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.organization_id == organization_id,
                ExternalIdentity.user_id == user_id,
                ExternalIdentity.is_active == True,
            )
        )
        return list(res.scalars().all())

    async def link_identity(
        self,
        organization_id: UUID,
        user_id: UUID,
        integration_id: UUID,
        provider: str,
        external_account_id: str,
        external_display_name: Optional[str] = None,
        verified_via_oauth: bool = True,
    ) -> ExternalIdentity:
        """Create or refresh the link between an AI-TPM user and their real external account.

        Idempotent for the SAME user re-connecting the SAME external account (e.g. re-running
        OAuth): updates the existing active row rather than duplicating it. Raises ValueError
        if that external_account_id is already actively linked to a DIFFERENT user in this
        organization -- one external account must never silently attach to two AI-TPM users.
        """
        conflict_res = await self.session.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.organization_id == organization_id,
                ExternalIdentity.provider == provider,
                ExternalIdentity.external_account_id == external_account_id,
                ExternalIdentity.is_active == True,
            )
        )
        existing_for_account = conflict_res.scalar_one_or_none()
        if existing_for_account and existing_for_account.user_id != user_id:
            raise ValueError(
                f"This {provider} account is already linked to a different user in this organization."
            )

        own_res = await self.session.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.organization_id == organization_id,
                ExternalIdentity.user_id == user_id,
                ExternalIdentity.provider == provider,
                ExternalIdentity.is_active == True,
            )
        )
        identity = own_res.scalar_one_or_none()
        if identity:
            identity.external_account_id = external_account_id
            identity.external_display_name = external_display_name
            identity.integration_id = integration_id
            identity.verified_via_oauth = verified_via_oauth
        else:
            identity = ExternalIdentity(
                organization_id=organization_id,
                user_id=user_id,
                integration_id=integration_id,
                provider=provider,
                external_account_id=external_account_id,
                external_display_name=external_display_name,
                verified_via_oauth=verified_via_oauth,
                is_active=True,
            )
            self.session.add(identity)
        await self.session.flush()

        await self.audit_service.log(
            organization_id=organization_id,
            user_id=user_id,
            action="external_identity:link",
            details={"provider": provider, "external_account_id": external_account_id},
        )
        return identity

    async def unlink_identity(self, organization_id: UUID, identity_id: UUID, acting_user: User) -> ExternalIdentity:
        """Deactivate an identity link (soft, matching revoke_oauth_token's is_active=False
        convention -- preserves history rather than hard-deleting). Tenant-scoped in the same
        query, not fetch-then-check. Self-service (the identity's own owner) or OrgAdmin/
        SuperAdmin -- permission is checked BEFORE mutating anything, matching
        UserService.assign_role/revoke_role's convention, not after.

        Raises LookupError if not found in this organization, PermissionError if the acting
        user is neither the identity's owner nor an org admin.
        """
        res = await self.session.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.id == identity_id,
                ExternalIdentity.organization_id == organization_id,
            )
        )
        identity = res.scalar_one_or_none()
        if not identity:
            raise LookupError(f"External identity '{identity_id}' not found in this organization.")

        if identity.user_id != acting_user.id:
            role_names = {r.name for r in acting_user.roles}
            if not role_names & ADMIN_ROLES:
                raise PermissionError("Only the identity's own owner or an OrgAdmin/SuperAdmin may unlink it.")

        identity.is_active = False
        await self.session.flush()

        await self.audit_service.log(
            organization_id=organization_id,
            user_id=acting_user.id,
            action="external_identity:unlink",
            details={"provider": identity.provider, "identity_id": str(identity.id)},
        )
        return identity
