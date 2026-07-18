from fastapi import APIRouter
from app.api.v1 import auth, users, integrations, context

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(context.router, prefix="/context", tags=["context"])
