from fastapi import APIRouter
from app.api.v1 import auth, users, integrations

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
