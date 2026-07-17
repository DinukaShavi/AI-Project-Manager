from sqlalchemy import Column, String, ForeignKey, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class Recommendation(Base):
    __tablename__ = "recommendations"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    recommendation_type = Column(String(100), nullable=False)
    score = Column(Numeric(precision=3, scale=2), nullable=False)
    status = Column(String(50), nullable=False, default="active") # 'active', 'dismissed', 'accepted'

    # Relationships
    project = relationship("Project", back_populates="recommendations")
