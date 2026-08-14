from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.auth import LoginRequest
from app.schemas.token import Token, TokenRefresh
from app.services.auth import AuthService

router = APIRouter()

@router.post("/login", response_model=Token)
async def login(
    login_in: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate credentials and issue Access and Refresh tokens."""
    auth_service = AuthService(db)
    client_ip = request.client.host if request.client else None
    tokens = await auth_service.login(login_in.email, login_in.password, ip_address=client_ip)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
    access_token, refresh_token = tokens
    return Token(access_token=access_token, refresh_token=refresh_token)

@router.post("/refresh", response_model=Token)
async def refresh(
    refresh_in: TokenRefresh,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Accept refresh token, rotate keys, and issue fresh access and refresh tokens."""
    auth_service = AuthService(db)
    client_ip = request.client.host if request.client else None
    tokens = await auth_service.refresh_tokens(refresh_in.refresh_token, ip_address=client_ip)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    access_token, refresh_token = tokens
    return Token(access_token=access_token, refresh_token=refresh_token)
