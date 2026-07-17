from sqlalchemy import Column, String, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class Integration(Base):
    __tablename__ = "integrations"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False) # 'github', 'jira', 'slack', 'google_calendar'
    is_active = Column(Boolean, default=True)

    # Relationships
    organization = relationship("Organization", back_populates="integrations")
    oauth_token = relationship("OAuthToken", back_populates="integration", uselist=False, cascade="all, delete-orphan")

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    integration_id = Column(UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), unique=True, nullable=False)
    encrypted_access_token = Column(Text, nullable=False)
    encrypted_refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(ARRAY(String), nullable=True)

    # Relationships
    integration = relationship("Integration", back_populates="oauth_token")
