from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class AnalyticsMetric(Base):
    __tablename__ = "analytics_metrics"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Numeric(precision=12, scale=4), nullable=False)
    dimension_metadata = Column("metadata", JSONB, nullable=True) # Contextual tags (e.g. developer_urn)
    recorded_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    project = relationship("Project", back_populates="analytics_metrics")
