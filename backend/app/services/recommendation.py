from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.recommendation import Recommendation
from app.services.audit import AuditService

VALID_RECOMMENDATION_ACTIONS = {"dismiss": "dismissed", "accept": "accepted"}

class RecommendationService:
    def __init__(self, session: AsyncSession):
        """Recommendation Service managing persisted AI-generated team suggestions
        (detailed_component_architecture.md section 7: Risk Scoring -> Deduplication ->
        Recommendation Log)."""
        self.session = session

    async def list_recommendations(
        self,
        organization_id: UUID,
        status: Optional[str] = None,
        recommendation_type: Optional[str] = None
    ) -> List[Recommendation]:
        """Fetch recommendations scoped to the caller's organization, per api_contract.md
        section 12.A (`GET /api/v1/recommendations?status=active&type=overload`)."""
        query = select(Recommendation).where(Recommendation.organization_id == organization_id)
        if status:
            query = query.where(Recommendation.status == status)
        if recommendation_type:
            query = query.where(Recommendation.recommendation_type == recommendation_type)
        query = query.order_by(Recommendation.score.desc(), Recommendation.created_at.desc())

        res = await self.session.execute(query)
        return res.scalars().all()

    async def persist_recommendations(
        self,
        organization_id: UUID,
        project_id: UUID,
        recommendations: List[Dict[str, Any]]
    ) -> List[Recommendation]:
        """Persist RecommendationEngine output into the recommendations table (the
        'Recommendation Log' stage). Applies the documented Deduplication & Relevance
        Filters stage: an identical still-active recommendation (same project, type, and
        title) is not re-inserted on repeated runs against unchanged conditions."""
        if not recommendations:
            return []

        existing_res = await self.session.execute(
            select(Recommendation.recommendation_type, Recommendation.title).where(
                Recommendation.organization_id == organization_id,
                Recommendation.project_id == project_id,
                Recommendation.status == "active",
            )
        )
        existing_keys = {(rtype, title) for rtype, title in existing_res.all()}

        created: List[Recommendation] = []
        for rec in recommendations:
            rtype = rec.get("recommendation_type", "general")
            title = rec.get("title", "")
            key = (rtype, title)
            if key in existing_keys:
                continue
            existing_keys.add(key)

            row = Recommendation(
                organization_id=organization_id,
                project_id=project_id,
                title=title,
                description=rec.get("description", ""),
                recommendation_type=rtype,
                score=rec.get("score", 0.0),
                status="active",
            )
            self.session.add(row)
            created.append(row)

        if created:
            await self.session.commit()
            for row in created:
                await self.session.refresh(row)
        return created

    async def apply_action(
        self,
        recommendation_id: UUID,
        organization_id: UUID,
        action: str,
        user_id: Optional[UUID] = None,
    ) -> Recommendation:
        """Apply a user action to a recommendation, per implementation_roadmap.md Milestone 15
        (`POST /api/v1/recommendations/{id}/action`) and ui_ux_design.md section 13's
        documented Recommendations Console actions: "Dismiss recommendation (logs feedback),
        Accept recommendation (triggers workflow)."

        Only the status transition and audit-log ("logs feedback") side of "Dismiss" /
        "Accept" is implemented here. The "triggers workflow" clause for Accept is NOT
        implemented -- no document specifies which workflow template an accepted
        recommendation should trigger, with what parameters, or under what DAG, so
        inventing that mapping would be fabricating undocumented architecture rather than
        implementing a documented one. A future turn can wire this once that mapping is
        actually specified.

        Raises ValueError if `action` isn't one of the two documented values, or LookupError
        if the recommendation doesn't exist / belongs to another organization.
        """
        if action not in VALID_RECOMMENDATION_ACTIONS:
            raise ValueError(f"Unsupported action '{action}'. Must be one of: {sorted(VALID_RECOMMENDATION_ACTIONS)}.")

        res = await self.session.execute(
            select(Recommendation).where(
                Recommendation.id == recommendation_id,
                Recommendation.organization_id == organization_id,
            )
        )
        rec = res.scalar_one_or_none()
        if not rec:
            raise LookupError(f"Recommendation '{recommendation_id}' not found in this organization.")

        rec.status = VALID_RECOMMENDATION_ACTIONS[action]

        await AuditService(self.session).log(
            organization_id=organization_id,
            user_id=user_id,
            action=f"recommendation:{action}",
            details={"recommendation_id": str(recommendation_id), "title": rec.title, "recommendation_type": rec.recommendation_type},
        )

        await self.session.commit()
        await self.session.refresh(rec)
        return rec
