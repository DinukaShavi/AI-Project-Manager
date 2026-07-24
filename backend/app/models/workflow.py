from sqlalchemy import Column, String, ForeignKey, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base_class import Base, SoftDeleteMixin

class WorkflowDefinition(Base, SoftDeleteMixin):
    __tablename__ = "workflows"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    trigger_event = Column(String(255), nullable=True, default="manual")
    dag_structure = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, default=True)

    # Relationships
    organization = relationship("Organization", back_populates="workflows")
    executions = relationship("WorkflowExecution", foreign_keys="WorkflowExecution.workflow_id", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True)
    workflow_definition_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True)
    status = Column(String(50), nullable=False, default="running")
    current_step = Column(String(255), nullable=True)
    state_payload = Column(JSONB, nullable=False, default=dict)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workflow = relationship("WorkflowDefinition", foreign_keys=[workflow_id], back_populates="executions")
    agent_executions = relationship("AgentExecution", back_populates="workflow_execution", cascade="all, delete-orphan")
