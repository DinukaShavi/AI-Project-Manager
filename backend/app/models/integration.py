from sqlalchemy import Column, String, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class Integration(Base):
    __tablename__ = "integrations"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False) # 'github', 'jira', 'slack', 'google_calendar'
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    # Which external site/team/org this connection actually points to -- e.g. Slack team id
    # ("T0123...") + name, Jira site id + name, GitHub org id + login. Populated automatically
    # when the OAuth provider's response makes this trustworthily available (see
    # IntegrationService._extract_identity_from_token_response); left null otherwise rather
    # than guessed.
    external_workspace_id = Column(String(255), nullable=True)
    external_workspace_name = Column(String(255), nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="integrations")
    oauth_token = relationship("OAuthToken", back_populates="integration", uselist=False, cascade="all, delete-orphan")

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_id = Column(UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), unique=True, nullable=False)
    encrypted_access_token = Column(Text, nullable=False)
    encrypted_refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(ARRAY(String), nullable=True)

    # Relationships
    integration = relationship("Integration", back_populates="oauth_token")
