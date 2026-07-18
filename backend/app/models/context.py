from sqlalchemy import Column, String, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.db.base_class import Base

class ContextChunk(Base):
    __tablename__ = "context_chunks"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    source_type = Column(String(100), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSONB, nullable=False, default=dict)

    # Relationships
    embeddings = relationship("ContextEmbedding", back_populates="chunk", cascade="all, delete-orphan")


class ContextEmbedding(Base):
    __tablename__ = "context_embeddings"

    chunk_id = Column(UUID(as_uuid=True), ForeignKey("context_chunks.id", ondelete="CASCADE"), nullable=False)
    model_name = Column(String(100), nullable=False, default="text-embedding-3-small")
    dimension = Column(Integer, nullable=False, default=1536)
    embedding = Column(Vector(1536), nullable=False)

    # Relationships
    chunk = relationship("ContextChunk", back_populates="embeddings")
