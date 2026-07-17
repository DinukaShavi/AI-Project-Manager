from sqlalchemy import Column, String, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    agent_type = Column(String(50), nullable=False)
    version = Column(String(20), nullable=False)
    prompt_text = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint('agent_type', 'version', name='uq_agent_type_version'),
    )

class ModelConfiguration(Base):
    __tablename__ = "model_configurations"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    model_name = Column(String(100), nullable=False)
    parameters = Column(JSONB, nullable=False, default=dict)

    # Relationships
    organization = relationship("Organization", back_populates="model_configurations")

class AgentExecution(Base):
    __tablename__ = "agent_executions"

    workflow_execution_id = Column(UUID(as_uuid=True), ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True)
    agent_name = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="running")
    thought_log = Column(Text, nullable=True)
    agent_output = Column(JSONB, nullable=True)

    # Relationships
    workflow_execution = relationship("WorkflowExecution", back_populates="agent_executions")
    tool_executions = relationship("ToolExecution", back_populates="agent_execution", cascade="all, delete-orphan")

class ToolExecution(Base):
    __tablename__ = "tool_executions"

    agent_execution_id = Column(UUID(as_uuid=True), ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(100), nullable=False)
    tool_parameters = Column(JSONB, nullable=False)
    tool_output = Column(JSONB, nullable=True)
    status = Column(String(50), nullable=False) # 'success', 'failure'
    error_message = Column(Text, nullable=True)

    # Relationships
    agent_execution = relationship("AgentExecution", back_populates="tool_executions")
