import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tenant import Organization, User
from app.models.invitation import Invitation
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.repositories.role import RoleRepository
from app.schemas.user import UserCreate
from app.services.audit import AuditService

INVITATION_EXPIRY_DAYS = 7

class OrganizationService:
    def __init__(self, session: AsyncSession):
        """Organization Service for org settings, membership lookups, and (per the AI-TPM
        product vision) organization bootstrap + team invitation."""
        self.session = session
        self.repository = OrganizationRepository(session)
        self.user_repository = UserRepository(session)
        self.role_repository = RoleRepository(session)
        self.audit_service = AuditService(session)

    async def get_settings(self, organization_id: UUID) -> Optional[Organization]:
        """Fetch organization settings, per docs/api_contract.md 'Get Organization Settings'."""
        return await self.repository.get(organization_id)

    async def list_members(self, organization_id: UUID) -> List[User]:
        """List all members of an organization with their roles, for the Settings Console's
        team member roles table (ui_ux_design.md screen #20)."""
        return await self.user_repository.list_by_organization(organization_id)

    async def create_organization_with_admin(
        self,
        org_name: str,
        admin_email: str,
        admin_full_name: str,
        admin_password: str,
        domain: Optional[str] = None,
    ) -> Tuple[Organization, User]:
        """Bootstrap a brand-new organization together with its founding OrgAdmin user, in one
        transaction. This is the product's actual "PM creates an organization" step -- there
        was previously no way to create an organization at all outside direct DB/seed access,
        which meant POST /users/register's required organization_id had nothing to point at
        for a genuinely new tenant.

        Reuses UserService.create_user()'s existing, audited registration path for the admin
        account (grants the default 'Developer' role + logs 'auth:register') rather than
        duplicating user-creation logic, then additionally grants 'OrgAdmin' so the founder can
        immediately invite teammates and manage the organization.

        Raises ValueError if the domain is already taken or the admin email is already
        registered anywhere in the system (User.email is globally unique).
        """
        from app.services.user import UserService

        if domain:
            existing_domain = await self.session.execute(select(Organization).where(Organization.domain == domain))
            if existing_domain.scalar_one_or_none():
                raise ValueError(f"An organization with domain '{domain}' already exists.")

        existing_user = await self.user_repository.get_by_email(admin_email)
        if existing_user:
            raise ValueError(f"A user with email '{admin_email}' already exists. Please log in instead.")

        org = Organization(name=org_name, domain=domain)
        self.session.add(org)
        await self.session.flush()

        user_service = UserService(self.session)
        admin_user = await user_service.create_user(UserCreate(
            email=admin_email,
            full_name=admin_full_name,
            organization_id=org.id,
            password=admin_password,
        ))

        org_admin_role = await self.role_repository.get_by_name("OrgAdmin")
        if org_admin_role:
            await self.session.refresh(admin_user, attribute_names=["roles"])
            if org_admin_role not in admin_user.roles:
                admin_user.roles.append(org_admin_role)
                await self.session.flush()

        await self.audit_service.log(
            organization_id=org.id,
            user_id=admin_user.id,
            action="organization:create",
            details={"organization_name": org_name, "admin_email": admin_email},
        )
        return org, admin_user

    async def create_invitation(
        self,
        organization_id: UUID,
        email: str,
        role_name: str,
        invited_by_user_id: UUID,
    ) -> Invitation:
        """Create a single-use, expiring invitation link for a teammate to join this
        organization. No email-sending infrastructure exists in this deployment, so delivery
        is the inviting admin's own responsibility (copy the link, send it however they
        normally reach their team) -- the token itself is the real, functioning artifact,
        not a simulated "email sent" side effect.

        Raises ValueError if role_name doesn't exist, or if the email already belongs to a
        member of this organization.
        """
        role = await self.role_repository.get_by_name(role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' does not exist.")

        existing_user = await self.user_repository.get_by_email(email)
        if existing_user and existing_user.organization_id == organization_id:
            raise ValueError(f"'{email}' is already a member of this organization.")

        # Superseding any still-pending invite for the same email keeps at most one valid
        # token per (organization, email) outstanding at a time.
        existing_res = await self.session.execute(
            select(Invitation).where(
                Invitation.organization_id == organization_id,
                Invitation.email == email,
                Invitation.status == "pending",
            )
        )
        for stale in existing_res.scalars().all():
            stale.status = "revoked"

        invitation = Invitation(
            organization_id=organization_id,
            email=email,
            invited_by_user_id=invited_by_user_id,
            role_name=role_name,
            token=secrets.token_urlsafe(32),
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(days=INVITATION_EXPIRY_DAYS),
        )
        self.session.add(invitation)
        await self.session.flush()

        await self.audit_service.log(
            organization_id=organization_id,
            user_id=invited_by_user_id,
            action="invitation:create",
            details={"invitation_id": str(invitation.id), "email": email, "role": role_name},
        )
        return invitation

    async def list_invitations(self, organization_id: UUID) -> List[Invitation]:
        """List all invitations for an organization, newest first."""
        res = await self.session.execute(
            select(Invitation)
            .where(Invitation.organization_id == organization_id)
            .order_by(Invitation.created_at.desc())
        )
        return list(res.scalars().all())

    async def revoke_invitation(self, invitation_id: UUID, organization_id: UUID, acting_user_id: UUID) -> Invitation:
        """Revoke a pending invitation. Tenant-scoped in the same query (not fetch-then-check)
        so a cross-tenant invitation_id is indistinguishable from a nonexistent one."""
        res = await self.session.execute(
            select(Invitation).where(Invitation.id == invitation_id, Invitation.organization_id == organization_id)
        )
        invitation = res.scalar_one_or_none()
        if not invitation:
            raise LookupError(f"Invitation '{invitation_id}' not found in this organization.")

        invitation.status = "revoked"
        await self.session.flush()

        await self.audit_service.log(
            organization_id=organization_id,
            user_id=acting_user_id,
            action="invitation:revoke",
            details={"invitation_id": str(invitation.id), "email": invitation.email},
        )
        return invitation

    async def accept_invitation(self, token: str, full_name: str, password: str) -> User:
        """Accept an invitation and create the invited user's account under the inviting
        organization, with the role specified at invite time.

        Raises LookupError if the token doesn't match any invitation, or ValueError if it's
        already been used/revoked, has expired, or an account with that email already exists.
        """
        res = await self.session.execute(select(Invitation).where(Invitation.token == token))
        invitation = res.scalar_one_or_none()
        if not invitation:
            raise LookupError("Invalid invitation link.")

        if invitation.status != "pending":
            raise ValueError(f"This invitation is no longer valid (status: {invitation.status}).")

        if invitation.expires_at <= datetime.now(timezone.utc):
            invitation.status = "expired"
            await self.session.flush()
            raise ValueError("This invitation has expired. Ask an organization admin to send a new one.")

        existing_user = await self.user_repository.get_by_email(invitation.email)
        if existing_user:
            raise ValueError("An account with this email already exists. Please log in instead.")

        from app.services.user import UserService
        user_service = UserService(self.session)
        new_user = await user_service.create_user(UserCreate(
            email=invitation.email,
            full_name=full_name,
            organization_id=invitation.organization_id,
            password=password,
        ))

        invited_role = await self.role_repository.get_by_name(invitation.role_name)
        if invited_role:
            await self.session.refresh(new_user, attribute_names=["roles"])
            if invited_role not in new_user.roles:
                new_user.roles.append(invited_role)
                await self.session.flush()

        invitation.status = "accepted"
        invitation.accepted_at = datetime.now(timezone.utc)
        invitation.accepted_user_id = new_user.id
        await self.session.flush()

        await self.audit_service.log(
            organization_id=invitation.organization_id,
            user_id=new_user.id,
            action="invitation:accept",
            details={"invitation_id": str(invitation.id), "email": invitation.email},
        )
        return new_user
