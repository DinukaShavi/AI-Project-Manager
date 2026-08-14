from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.tenant import User
from app.models.project import Project
from app.services.context import ContextEngineService
from app.context.graph import ProjectKnowledgeGraph

router = APIRouter()

async def _verify_project_ownership(db: AsyncSession, project_id: UUID, organization_id) -> None:
    """Shared tenant-ownership guard (matching analytics.py's identical pattern) -- without
    this check, any authenticated user could read another organization's project knowledge
    graph by guessing a project_id."""
    res = await db.execute(
        select(Project).where(Project.id == project_id, Project.organization_id == organization_id, Project.deleted_at == None)
    )
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found in this organization.")

class IndexRequest(BaseModel):
    source_type: str = Field(..., description="Source entity type (e.g. pr, issue, doc, chat)")
    source_id: UUID
    text: str = Field(..., description="Raw text content to chunk and index")
    project_id: Optional[UUID] = None
    metadata: Optional[Dict[str, Any]] = None

class SearchRequest(BaseModel):
    query: Optional[str] = Field(None, description="Semantic search query")
    query_text: Optional[str] = Field(None, description="Semantic search query alias")
    project_id: Optional[UUID] = None
    top_k: int = Field(5, ge=1, le=50)

    def get_query(self) -> str:
        return self.query or self.query_text or ""

@router.post("/index", status_code=status.HTTP_201_CREATED)
async def index_document(
    payload: IndexRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Chunk, embed, and index a technical document into the Context Engine."""
    service = ContextEngineService(db)
    chunks = await service.index_document(
        organization_id=current_user.organization_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        text=payload.text,
        project_id=payload.project_id,
        metadata=payload.metadata
    )
    return {
        "status": "indexed",
        "chunks_indexed": len(chunks),
        "chunk_ids": [str(c.id) for c in chunks]
    }

@router.post("/search")
async def search_context(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Execute vector semantic search across indexed technical context."""
    service = ContextEngineService(db)
    search_q = payload.get_query()
    results = await service.search_context(
        organization_id=current_user.organization_id,
        query_text=search_q,
        project_id=payload.project_id,
        top_k=payload.top_k
    )
    return {
        "query": search_q,
        "results_count": len(results),
        "results": results
    }

@router.get("/projects/{project_id}/graph", status_code=status.HTTP_200_OK)
async def get_project_graph(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve the current unified Knowledge Graph state for a project, per
    api_contract.md section 8.A. Scoped to the authenticated user's organization; the
    project must belong to it or a generic 404 is returned (no existence-leak)."""
    await _verify_project_ownership(db, project_id, current_user.organization_id)

    graph = ProjectKnowledgeGraph()
    await graph.load_from_db(db, current_user.organization_id, project_id)

    return {
        "nodes": [
            {"urn": node.urn, "type": node.type, "properties": node.properties}
            for node in graph.nodes.values()
        ],
        "edges": [
            {"source": edge.source_urn, "target": edge.target_urn, "relation": edge.relation_type, "weight": edge.weight}
            for edge in graph.edges
        ]
    }
