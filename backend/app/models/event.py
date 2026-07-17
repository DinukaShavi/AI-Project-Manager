from sqlalchemy import Column, String, ForeignKey, Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base_class import Base

class Event(Base):
    __tablename__ = "events"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    routing_key = Column(String(255), nullable=False, index=True)
    payload = Column(JSONB, nullable=False)
    processed = Column(Boolean, default=False, index=True)
    retry_count = Column(Integer, default=0)
    error_log = Column(Text, nullable=True)
