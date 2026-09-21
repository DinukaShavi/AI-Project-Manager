from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.embeddings import get_embedding_generator
from app.context.graph import ProjectKnowledgeGraph
from app.models.context import ContextChunk
from app.models.graph import ContextSnapshot
from app.models.project import Project

SNAPSHOT_THROTTLE = timedelta(minutes=15)
RECENT_CHUNK_LIMIT = 10
BOTTLENECK_DISPLAY_LIMIT = 5


class ContextSnapshotService:
    """Generates real, point-in-time ContextSnapshot rows from real already-ingested data
    (Phase 58 ContextChunks, Phase 59 KnowledgeGraphEdges) -- the second half of the
    "centralized context" gap the original product audit flagged; the first half
    (real ingestion into the vector store and graph) was closed by Phases 58/59.

    The summary is templated from real structured data, not LLM-narrated -- embedded with the
    same embedding generator ContextChunks already use, so this adds no new model-call cost or
    dependency (a decision made explicitly, not a shortcut: see docs/phase68_context_snapshot_population.md).
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedding_generator = get_embedding_generator()

    async def get_latest_snapshot(self, organization_id: UUID, project_id: UUID) -> Optional[ContextSnapshot]:
        res = await self.session.execute(
            select(ContextSnapshot)
            .where(ContextSnapshot.organization_id == organization_id, ContextSnapshot.project_id == project_id)
            .order_by(ContextSnapshot.snapshot_timestamp.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def is_snapshot_stale(self, organization_id: UUID, project_id: UUID) -> bool:
        """True if the project has no snapshot yet, or its latest one is older than the
        throttle window -- the gate `handle_event` checks before auto-regenerating."""
        latest = await self.get_latest_snapshot(organization_id, project_id)
        if latest is None:
            return True
        return datetime.now(timezone.utc) - latest.snapshot_timestamp > SNAPSHOT_THROTTLE

    async def _gather_recent_chunks(self, organization_id: UUID, project_id: UUID) -> List[ContextChunk]:
        res = await self.session.execute(
            select(ContextChunk)
            .where(ContextChunk.organization_id == organization_id, ContextChunk.project_id == project_id)
            .order_by(ContextChunk.created_at.desc())
            .limit(RECENT_CHUNK_LIMIT)
        )
        return list(res.scalars().all())

    async def _gather_bottlenecks(self, organization_id: UUID, project_id: UUID) -> List[Dict[str, Any]]:
        graph = ProjectKnowledgeGraph()
        await graph.load_from_db(self.session, organization_id, project_id)
        return graph.find_bottleneck_clusters()

    def _build_summary_text(self, project_name: str, chunks: List[ContextChunk], bottlenecks: List[Dict[str, Any]]) -> str:
        lines = [f"Project: {project_name}"]

        if not chunks:
            lines.append("No recent real activity indexed for this project yet.")
        else:
            counts: Dict[str, int] = {}
            for c in chunks:
                counts[c.source_type] = counts.get(c.source_type, 0) + 1
            counts_text = ", ".join(f"{n} {t}" for t, n in counts.items())
            lines.append(f"Recent activity ({len(chunks)} real event(s) indexed): {counts_text}.")
            for c in chunks[:5]:
                title = (c.metadata_json or {}).get("title") or c.content[:60]
                lines.append(f"  - [{c.source_type}] {title}")

        if not bottlenecks:
            lines.append("No knowledge graph bottlenecks detected.")
        else:
            lines.append(f"Knowledge graph bottlenecks ({len(bottlenecks)} entit(y/ies) with 2+ blocking relationships):")
            for b in bottlenecks[:BOTTLENECK_DISPLAY_LIMIT]:
                lines.append(f"  - {b['urn']} (blocking={b['blocking_count']}, blocked_by={b['blocked_by_count']})")

        return "\n".join(lines)

    async def generate_snapshot(self, organization_id: UUID, project_id: UUID) -> ContextSnapshot:
        """Assemble real data, embed a templated summary of it, and persist a new
        ContextSnapshot row. Raises LookupError if the project doesn't belong to this org."""
        project = await self.session.get(Project, project_id)
        if not project or project.organization_id != organization_id:
            raise LookupError("Project not found in this organization.")

        chunks = await self._gather_recent_chunks(organization_id, project_id)
        bottlenecks = await self._gather_bottlenecks(organization_id, project_id)
        summary_text = self._build_summary_text(project.name, chunks, bottlenecks)
        embedding_vector = await self.embedding_generator.generate_embedding(summary_text)

        state_payload = {
            "summary": summary_text,
            "recent_activity": [
                {
                    "source_type": c.source_type,
                    "title": (c.metadata_json or {}).get("title"),
                    "created_at": c.created_at.isoformat(),
                }
                for c in chunks
            ],
            "bottlenecks": bottlenecks,
        }

        snapshot = ContextSnapshot(
            organization_id=organization_id,
            project_id=project_id,
            snapshot_timestamp=datetime.now(timezone.utc),
            state_payload=state_payload,
            summary_embedding=embedding_vector,
        )
        self.session.add(snapshot)
        await self.session.commit()
        await self.session.refresh(snapshot)
        return snapshot
