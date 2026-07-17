from sqlalchemy import Column, String, ForeignKey, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base_class import Base, SoftDeleteMixin

class WorkflowDefinition(Base, SoftDeleteMixin):
    # Mapping to table 'workflows' by defining CustomBase mapping override if needed, or by setting __tablename__ explicitly
    __tablename__ = "workflows"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    trigger_event = Column(String(255), nullable=False)
    dag_definition = Column(JSONB, nullable=False)
    is_active = Column(Boolean, default=True)

    # Relationships
    organization = relationship("Organization", back_populates="workflows")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")

class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False, default="pending") # 'running', 'suspended', 'completed', 'failed', 'cancelled'
    current_step = Column(String(255), nullable=True)
    execution_state = Column(JSONB, nullable=False, default=dict)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workflow = relationship("WorkflowDefinition", back_populates="executions")
    agent_executions = relationship("AgentExecution", back_populates="workflow_execution", cascade="all, delete-orphan")
