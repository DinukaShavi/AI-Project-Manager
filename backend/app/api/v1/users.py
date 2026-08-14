from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.schemas.user import UserCreate, UserRead
from app.services.user import UserService
from app.models.tenant import User
from app.core.rbac_pdp import ADMIN_ROLES

router = APIRouter()

class RoleAssignRequest(BaseModel):
    role_name: str = Field(..., description="One of: SuperAdmin, OrgAdmin, ProjectManager, Developer, Viewer")


def _require_org_admin(current_user: User) -> None:
    role_names = {r.name for r in current_user.roles}
    if not role_names & ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OrgAdmin or SuperAdmin roles may manage user roles."
        )

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user account."""
    user_service = UserService(db)
    try:
        user = await user_service.create_user(user_in)
        await db.commit()
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: User = Depends(get_current_user)
):
    """Fetch the active authenticated user profile details."""
    return current_user

@router.post("/{user_id}/roles", response_model=UserRead)
async def assign_role(
    user_id: UUID,
    payload: RoleAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Grant a role to a user in the caller's own organization. OrgAdmin/SuperAdmin only."""
    _require_org_admin(current_user)
    service = UserService(db)
    try:
        updated = await service.assign_role(user_id, payload.role_name, current_user)
        await db.commit()
        return updated
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

@router.delete("/{user_id}/roles/{role_name}", response_model=UserRead)
async def revoke_role(
    user_id: UUID,
    role_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke a role from a user in the caller's own organization. OrgAdmin/SuperAdmin only."""
    _require_org_admin(current_user)
    service = UserService(db)
    try:
        updated = await service.revoke_role(user_id, role_name, current_user)
        await db.commit()
        return updated
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
