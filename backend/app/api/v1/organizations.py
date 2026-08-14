from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.tenant import User
from app.services.organization import OrganizationService
from app.services.external_identity import ExternalIdentityService
from app.core.rbac_pdp import ADMIN_ROLES

router = APIRouter()


class CreateOrganizationRequest(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=255)
    admin_email: EmailStr
    admin_full_name: str = Field(..., min_length=1, max_length=255)
    admin_password: str = Field(..., min_length=8)
    domain: Optional[str] = Field(None, max_length=255)


class CreateInvitationRequest(BaseModel):
    email: EmailStr
    role_name: str = Field("Developer", description="One of: SuperAdmin, OrgAdmin, ProjectManager, Developer, Viewer")


class AcceptInvitationRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8)


def _require_org_admin(current_user: User) -> None:
    role_names = {r.name for r in current_user.roles}
    if not role_names & ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OrgAdmin or SuperAdmin roles may perform this action."
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: CreateOrganizationRequest,
    db: AsyncSession = Depends(get_db)
):
    """Bootstrap a brand-new organization together with its founding OrgAdmin account -- the
    product's actual "PM creates an organization" step. Unauthenticated, like /auth/login and
    /users/register: there is no authenticated context yet for a PM who doesn't have an
    organization at all. Does not auto-login; the caller logs in via POST /auth/login
    afterward, matching /users/register's existing behavior."""
    service = OrganizationService(db)
    try:
        org, admin_user = await service.create_organization_with_admin(
            org_name=payload.organization_name,
            admin_email=payload.admin_email,
            admin_full_name=payload.admin_full_name,
            admin_password=payload.admin_password,
            domain=payload.domain,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "organization_id": str(org.id),
        "name": org.name,
        "domain": org.domain,
        "admin_user": {
            "id": str(admin_user.id),
            "email": admin_user.email,
            "full_name": admin_user.full_name,
            "roles": [r.name for r in admin_user.roles],
        },
    }


@router.get("/settings", status_code=status.HTTP_200_OK)
async def get_organization_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the authenticated user's organization settings. Response shape matches
    docs/api_contract.md 'Get Organization Settings' exactly."""
    _require_org_admin(current_user)
    service = OrganizationService(db)
    org = await service.get_settings(current_user.organization_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    return {
        "organization_id": str(org.id),
        "name": org.name,
        "domain": org.domain,
        "allowed_email_domains": org.allowed_email_domains or [],
        "created_at": org.created_at
    }


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: CreateInvitationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Invite a teammate into the authenticated user's organization by email. OrgAdmin/
    SuperAdmin only. Returns the raw invitation token once, to the inviting admin -- there is
    no email-sending infrastructure in this deployment, so the admin is responsible for
    sending the resulting link (e.g. `${frontend_origin}/accept-invite?token=...`) themselves.
    This is a real, functioning single-use token, not a simulated "email sent" side effect."""
    _require_org_admin(current_user)
    service = OrganizationService(db)
    try:
        invitation = await service.create_invitation(
            organization_id=current_user.organization_id,
            email=payload.email,
            role_name=payload.role_name,
            invited_by_user_id=current_user.id,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "invitation_id": str(invitation.id),
        "email": invitation.email,
        "role": invitation.role_name,
        "status": invitation.status,
        "token": invitation.token,
        "expires_at": invitation.expires_at,
    }


@router.get("/invitations", status_code=status.HTTP_200_OK)
async def list_invitations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all invitations (pending, accepted, revoked, expired) for the authenticated user's
    organization. OrgAdmin/SuperAdmin only. Never returns the token -- it was already handed
    to the inviting admin once, at creation time."""
    _require_org_admin(current_user)
    service = OrganizationService(db)
    invitations = await service.list_invitations(current_user.organization_id)
    return {
        "invitations": [
            {
                "id": str(inv.id),
                "email": inv.email,
                "role": inv.role_name,
                "status": inv.status,
                "created_at": inv.created_at,
                "expires_at": inv.expires_at,
            }
            for inv in invitations
        ]
    }


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_200_OK)
async def revoke_invitation(
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke a pending invitation. OrgAdmin/SuperAdmin only."""
    _require_org_admin(current_user)
    service = OrganizationService(db)
    try:
        invitation = await service.revoke_invitation(invitation_id, current_user.organization_id, current_user.id)
        await db.commit()
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"invitation_id": str(invitation.id), "status": invitation.status}


@router.post("/invitations/{token}/accept", status_code=status.HTTP_201_CREATED)
async def accept_invitation(
    token: str,
    payload: AcceptInvitationRequest,
    db: AsyncSession = Depends(get_db)
):
    """Accept an invitation and create the invited user's account. Unauthenticated -- the
    invitee doesn't have an account yet. The invitation's stored organization_id and role_name
    (set by the inviting admin, never client-suppliable here) determine where the new account
    lands, not anything in this request body."""
    service = OrganizationService(db)
    try:
        user = await service.accept_invitation(token=token, full_name=payload.full_name, password=payload.password)
        await db.commit()
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "organization_id": str(user.organization_id),
        "roles": [r.name for r in user.roles],
    }


@router.get("/external-identities/me", status_code=status.HTTP_200_OK)
async def list_my_external_identities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List the authenticated user's own linked external accounts (Jira/GitHub/Slack/Google),
    for the Settings "Connected Accounts" panel. A provider absent from this list simply isn't
    linked yet for this user -- never backfilled with placeholder data. Never returns
    credential material; only the provider's stable account id and (when available) a
    display-only name/workspace, per ExternalIdentity's design."""
    service = ExternalIdentityService(db)
    identities = await service.list_identities_for_user(current_user.organization_id, current_user.id)
    return {
        "identities": [
            {
                "id": str(i.id),
                "provider": i.provider,
                "external_account_id": i.external_account_id,
                "external_display_name": i.external_display_name,
                "verified_via_oauth": i.verified_via_oauth,
            }
            for i in identities
        ]
    }


@router.delete("/external-identities/{identity_id}", status_code=status.HTTP_200_OK)
async def unlink_external_identity(
    identity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unlink an external identity. Self-service (the identity's own owner) or OrgAdmin/
    SuperAdmin. Tenant-scoped -- an identity belonging to another organization is
    indistinguishable from a nonexistent one."""
    service = ExternalIdentityService(db)
    try:
        identity = await service.unlink_identity(current_user.organization_id, identity_id, current_user)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    await db.commit()
    return {"identity_id": str(identity.id), "status": "unlinked"}


@router.get("/members", status_code=status.HTTP_200_OK)
async def list_organization_members(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List members of the authenticated user's organization with their assigned roles, for
    the Settings Console's team member roles table (ui_ux_design.md screen #20). Not part of
    api_contract.md's formal catalog (only 'Get Organization Settings' is documented there);
    added as a necessary complement to render that documented UI widget, same as the
    /users/{id}/roles endpoints added for role management."""
    _require_org_admin(current_user)
    service = OrganizationService(db)
    members = await service.list_members(current_user.organization_id)
    return {
        "members_count": len(members),
        "members": [
            {
                "id": str(m.id),
                "email": m.email,
                "full_name": m.full_name,
                "roles": [r.name for r in m.roles]
            }
            for m in members
        ]
    }
