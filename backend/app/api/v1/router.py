from fastapi import APIRouter
from app.api.v1 import auth, users, integrations, context, agents

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(context.router, prefix="/context", tags=["context"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
