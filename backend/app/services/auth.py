from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.services.user import UserService
from app.services.audit import AuditService
from app.models.tenant import User
from app.db.session import set_tenant_session_context

class AuthService:
    def __init__(self, session: AsyncSession):
        """Auth Service managing authentication operations and token issuance."""
        self.session = session
        self.user_service = UserService(session)
        self.audit_service = AuditService(session)

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user by checking email and verifying password hash."""
        user = await self.user_service.get_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def login(self, email: str, password: str, ip_address: Optional[str] = None) -> Optional[Tuple[str, str]]:
        """Log in a user, returning (access_token, refresh_token) or None if validation fails.
        Records an audit_logs entry for both successful and failed attempts (failed attempts
        are only attributable to a tenant when the email matches a real user; an unknown email
        has no organization to scope the audit row to)."""
        user = await self.user_service.get_by_email(email)
        password_valid = bool(user) and verify_password(password, user.hashed_password)

        if user:
            # Login is a pre-auth endpoint, so no tenant context is set on this session yet;
            # we do know the looked-up user's org, so set it explicitly for this RLS-protected write.
            await set_tenant_session_context(self.session, user.organization_id)
            await self.audit_service.log(
                organization_id=user.organization_id,
                user_id=user.id,
                action="auth:login_success" if password_valid else "auth:login_failed",
                details={"email": email},
                ip_address=ip_address
            )
            await self.session.commit()

        if not password_valid:
            return None

        # Generate short-lived access and long-lived refresh tokens
        access = create_access_token(user.id)
        refresh = create_refresh_token(user.id)
        return access, refresh

    async def refresh_tokens(self, refresh_token: str, ip_address: Optional[str] = None) -> Optional[Tuple[str, str]]:
        """Verify a refresh token and issue rotated access and refresh tokens.

        Audit logging note: AuditService.log() requires a real organization_id (it is not
        an Optional parameter on that schema), so a rejection can only be audited when an
        organization is genuinely, safely known -- never fabricated. An invalid signature,
        wrong token type, or missing 'sub' claim carries no verified identity at all (the
        token could be garbage), and a 'sub' pointing at a user_id with no matching row
        gives us a user_id but no organization to resolve it to. The one rejection case
        where a real organization IS known is a validly-signed token for a user who was
        found but has since been soft-deleted -- that case is audited below."""
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        user = await self.user_service.get_by_id(user_id)
        if not user:
            return None

        if user.is_deleted:
            await set_tenant_session_context(self.session, user.organization_id)
            await self.audit_service.log(
                organization_id=user.organization_id,
                user_id=user.id,
                action="auth:token_refresh_failed",
                details={"reason": "user_deleted"},
                ip_address=ip_address
            )
            await self.session.commit()
            return None

        # Rotate access and refresh tokens
        new_access = create_access_token(user.id)
        new_refresh = create_refresh_token(user.id)

        await set_tenant_session_context(self.session, user.organization_id)
        await self.audit_service.log(
            organization_id=user.organization_id,
            user_id=user.id,
            action="auth:token_refresh_success",
            details={},
            ip_address=ip_address
        )
        await self.session.commit()

        return new_access, new_refresh
