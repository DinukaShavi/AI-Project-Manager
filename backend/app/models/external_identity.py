from sqlalchemy import Column, String, ForeignKey, Boolean, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base_class import Base

class ExternalIdentity(Base):
    """Links an AI-TPM User to their real account on a connected external provider
    (Jira/GitHub/Slack/Google), scoped to the specific Integration (org+provider connection)
    it was established through. Never stores credentials -- those remain exclusively in
    OAuthToken. `external_account_id` is always the provider's stable account identifier
    (e.g. Slack user id, GitHub numeric user id, Jira accountId, Google `sub`), never an
    email -- `external_display_name` is a display-only hint, never a join key.

    Uniqueness is enforced only among ACTIVE rows (partial unique indexes) so that unlinking
    (is_active=False) and later re-linking the same external account to a different AI-TPM
    user doesn't collide with its own now-inactive history.
    """
    __tablename__ = "external_identities"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_id = Column(UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # 'github', 'jira', 'slack', 'google_calendar'
    external_account_id = Column(String(255), nullable=False)
    external_display_name = Column(String(255), nullable=True)
    verified_via_oauth = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    organization = relationship("Organization")
    user = relationship("User")
    integration = relationship("Integration")

    __table_args__ = (
        Index(
            "uq_external_identity_active_account",
            "organization_id", "provider", "external_account_id",
            unique=True, postgresql_where=text("is_active = true"),
        ),
        Index(
            "uq_external_identity_active_user_provider",
            "organization_id", "user_id", "provider",
            unique=True, postgresql_where=text("is_active = true"),
        ),
    )
