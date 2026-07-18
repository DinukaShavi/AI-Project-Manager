from sqlalchemy import Column, String, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.db.base_class import Base

class AgentMemory(Base):
    __tablename__ = "agent_memories"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    agent_type = Column(String(50), nullable=True)
    memory_type = Column(String(50), nullable=False) # 'short_term', 'long_term', 'entity'
    key = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)
    value_json = Column(JSONB, nullable=True)
    embedding = Column(Vector(1536), nullable=True)

    # Relationships
    project = relationship("Project", back_populates="agent_memories")
