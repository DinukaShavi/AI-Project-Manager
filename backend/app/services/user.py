from typing import Optional, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tenant import User
from app.schemas.user import UserCreate, UserUpdate
from app.repositories.user import UserRepository
from app.repositories.role import RoleRepository
from app.core.security import get_password_hash
from app.core.rbac_pdp import UserRole
from app.services.audit import AuditService
from app.db.session import set_tenant_session_context

DEFAULT_REGISTRATION_ROLE = "Developer"

class UserService:
    def __init__(self, session: AsyncSession):
        """User Service handling user-related business logic."""
        self.session = session
        self.repository = UserRepository(session)
        self.role_repository = RoleRepository(session)
        self.audit_service = AuditService(session)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch a user by their email address."""
        return await self.repository.get_by_email(email)

    async def get_by_id(self, user_id: Any) -> Optional[User]:
        """Fetch a user by their UUID."""
        return await self.repository.get(user_id)

    async def get_by_id_with_roles(self, user_id: Any) -> Optional[User]:
        """Fetch a user by their UUID with roles eager-loaded."""
        return await self.repository.get_by_id_with_roles(user_id)

    async def create_user(self, user_in: UserCreate) -> User:
        """Create a new user, hashing their password before saving."""
        existing_user = await self.get_by_email(user_in.email)
        if existing_user:
            raise ValueError(f"User with email {user_in.email} already exists.")
            
        hashed = get_password_hash(user_in.password)
        db_user = User(
            organization_id=user_in.organization_id,
            email=user_in.email,
            full_name=user_in.full_name,
            hashed_password=hashed,
            avatar_url=user_in.avatar_url
        )
        created = await self.repository.create(db_user)

        # Grant the default role so RBAC (ToolExecutor's PolicyDecisionPoint checks) has an
        # actual role to evaluate instead of always falling back to its hardcoded default.
        # `created` just became persistent via flush(), so its .roles collection is no longer
        # treated as "known empty" and must be explicitly (and async-safely) loaded via
        # refresh() before appending — a bare attribute access here would attempt an implicit
        # lazy-load outside the greenlet context and raise MissingGreenlet.
        default_role = await self.role_repository.get_by_name(DEFAULT_REGISTRATION_ROLE)
        if default_role:
            await self.session.refresh(created, attribute_names=["roles"])
            created.roles.append(default_role)
            await self.session.flush()

        # Registration is a pre-auth endpoint, so no tenant context is set on this session yet.
        await set_tenant_session_context(self.session, user_in.organization_id)
        await self.audit_service.log(
            organization_id=user_in.organization_id,
            user_id=created.id,
            action="auth:register",
            details={"email": user_in.email}
        )
        return created

    async def assign_role(self, target_user_id: UUID, role_name: str, acting_user: User) -> User:
        """Grant a role to a user within the acting user's own organization. Idempotent if the
        target already holds the role. Granting SuperAdmin additionally requires the acting
        user to already hold SuperAdmin, to prevent an OrgAdmin from self-escalating to
        platform-wide access."""
        role = await self.role_repository.get_by_name(role_name)
        if not role:
            raise LookupError(f"Role '{role_name}' does not exist.")

        target = await self.get_by_id_with_roles(target_user_id)
        if not target:
            raise LookupError(f"User '{target_user_id}' not found.")

        if target.organization_id != acting_user.organization_id:
            raise PermissionError("Cannot manage roles for a user outside your own organization.")

        acting_role_names = {r.name for r in acting_user.roles}
        if role.name == UserRole.SUPER_ADMIN.value and UserRole.SUPER_ADMIN.value not in acting_role_names:
            raise PermissionError("Only an existing SuperAdmin can grant the SuperAdmin role.")

        if role.name not in {r.name for r in target.roles}:
            target.roles.append(role)
            await self.session.flush()

        await self.audit_service.log(
            organization_id=acting_user.organization_id,
            user_id=acting_user.id,
            action="role:grant",
            details={"target_user_id": str(target.id), "target_email": target.email, "role": role.name}
        )
        return target

    async def revoke_role(self, target_user_id: UUID, role_name: str, acting_user: User) -> User:
        """Revoke a role from a user within the acting user's own organization. Idempotent if
        the target doesn't hold the role. Revoking SuperAdmin requires the acting user to
        already hold SuperAdmin, mirroring the grant restriction."""
        role = await self.role_repository.get_by_name(role_name)
        if not role:
            raise LookupError(f"Role '{role_name}' does not exist.")

        target = await self.get_by_id_with_roles(target_user_id)
        if not target:
            raise LookupError(f"User '{target_user_id}' not found.")

        if target.organization_id != acting_user.organization_id:
            raise PermissionError("Cannot manage roles for a user outside your own organization.")

        acting_role_names = {r.name for r in acting_user.roles}
        if role.name == UserRole.SUPER_ADMIN.value and UserRole.SUPER_ADMIN.value not in acting_role_names:
            raise PermissionError("Only an existing SuperAdmin can revoke the SuperAdmin role.")

        target.roles = [r for r in target.roles if r.name != role.name]
        await self.session.flush()

        await self.audit_service.log(
            organization_id=acting_user.organization_id,
            user_id=acting_user.id,
            action="role:revoke",
            details={"target_user_id": str(target.id), "target_email": target.email, "role": role.name}
        )
        return target

    async def update_user(self, db_user: User, user_in: UserUpdate) -> User:
        """Update user profile details and handle password updates."""
        update_dict = user_in.model_dump(exclude_unset=True)
        if "password" in update_dict and update_dict["password"]:
            update_dict["hashed_password"] = get_password_hash(update_dict.pop("password"))
        elif "password" in update_dict:
            update_dict.pop("password")
        return await self.repository.update(db_user, update_dict)
