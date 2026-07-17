from sqlalchemy import Column, String, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.db.base_class import Base, SoftDeleteMixin

class Project(Base, SoftDeleteMixin):
    __tablename__ = "projects"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    jira_project_key = Column(String(50), nullable=True)
    github_repo_name = Column(String(255), nullable=True)

    # Relationships
    workspace = relationship("Workspace", back_populates="projects")
    repositories = relationship("Repository", back_populates="project", cascade="all, delete-orphan")
    context_snapshots = relationship("ContextSnapshot", back_populates="project", cascade="all, delete-orphan")
    knowledge_graph_edges = relationship("KnowledgeGraphEdge", back_populates="project", cascade="all, delete-orphan")
    agent_memories = relationship("AgentMemory", back_populates="project", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="project", cascade="all, delete-orphan")
    analytics_metrics = relationship("AnalyticsMetric", back_populates="project", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="project", cascade="all, delete-orphan")

class Repository(Base):
    __tablename__ = "repositories"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    external_repo_id = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    clone_url = Column(Text, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="repositories")

class Meeting(Base):
    __tablename__ = "meetings"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    external_event_id = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    attendees = Column(JSONB, nullable=False, default=list)

    # Relationships
    project = relationship("Project", back_populates="meetings")
