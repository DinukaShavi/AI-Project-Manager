# Import all models for Alembic automatic generation to work
from app.db.base_class import Base # noqa
from app.models.tenant import Organization, Workspace, User, Role, Permission # noqa
from app.models.project import Project, Repository, Meeting # noqa
from app.models.integration import Integration, OAuthToken # noqa
from app.models.event import Event # noqa
from app.models.workflow import WorkflowDefinition, WorkflowExecution # noqa
from app.models.agent import PromptVersion, ModelConfiguration, AgentExecution, ToolExecution # noqa
from app.models.recommendation import Recommendation # noqa
from app.models.memory import AgentMemory # noqa
from app.models.graph import ContextSnapshot, KnowledgeGraphEdge # noqa
from app.models.context import ContextChunk, ContextEmbedding # noqa
from app.models.analytics import AnalyticsMetric # noqa
from app.models.notification import Notification # noqa
from app.models.audit import AuditLog # noqa
