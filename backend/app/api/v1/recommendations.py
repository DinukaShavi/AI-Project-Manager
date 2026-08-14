from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.tenant import User
from app.services.recommendation import RecommendationService

router = APIRouter()


class RecommendationActionRequest(BaseModel):
    action: str

@router.get("", status_code=status.HTTP_200_OK)
async def list_recommendations(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: 'active', 'dismissed', 'accepted'"),
    type_filter: Optional[str] = Query(None, alias="type", description="Filter by recommendation_type, e.g. 'overload', 'risk_delay'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch active team suggestions, per api_contract.md section 12.A. Scoped to the
    authenticated user's organization -- tenant identity is never client-supplied."""
    service = RecommendationService(db)
    recommendations = await service.list_recommendations(
        organization_id=current_user.organization_id,
        status=status_filter,
        recommendation_type=type_filter
    )
    return {
        "recommendations": [
            {
                "id": str(r.id),
                "title": r.title,
                "description": r.description,
                "score": float(r.score),
                "created_at": r.created_at
            }
            for r in recommendations
        ]
    }


@router.post("/{recommendation_id}/action", status_code=status.HTTP_200_OK)
async def apply_recommendation_action(
    recommendation_id: UUID,
    payload: RecommendationActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Apply an action to a recommendation, per implementation_roadmap.md Milestone 15
    (`POST /api/v1/recommendations/{id}/action`). Supported actions (ui_ux_design.md section
    13): 'dismiss' and 'accept'. Scoped to the authenticated user's organization -- a
    recommendation belonging to another organization is indistinguishable from a
    nonexistent one (404)."""
    service = RecommendationService(db)
    try:
        rec = await service.apply_action(
            recommendation_id=recommendation_id,
            organization_id=current_user.organization_id,
            action=payload.action,
            user_id=current_user.id,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "id": str(rec.id),
        "status": rec.status,
        "title": rec.title,
    }
