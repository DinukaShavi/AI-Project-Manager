from sqlalchemy import Column, String, ForeignKey, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.db.base_class import Base

class ContextSnapshot(Base):
    __tablename__ = "context_snapshots"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    snapshot_timestamp = Column(DateTime(timezone=True), nullable=False)
    state_payload = Column(JSONB, nullable=False)
    summary_embedding = Column(Vector(1536), nullable=False)

    # Relationships
    project = relationship("Project", back_populates="context_snapshots")

class KnowledgeGraphEdge(Base):
    __tablename__ = "knowledge_graph_edges"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_urn = Column(String(255), nullable=False)
    target_urn = Column(String(255), nullable=False)
    relation_type = Column(String(100), nullable=False)
    weight = Column(Numeric(precision=3, scale=2), default=1.0)

    # Relationships
    project = relationship("Project", back_populates="knowledge_graph_edges")
