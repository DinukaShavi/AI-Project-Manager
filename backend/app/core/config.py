from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI-TPM"
    API_V1_STR: str = "/api/v1"
    
    # Security Configurations
    SECRET_KEY: str = "729cf3991bf890f5c1d686f06a0df682a87a2a1ff394142a7e7bcde57d81a95e"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database Configuration
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres_secure_pass_123"
    POSTGRES_DB: str = "aitpm"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: str = "5432"
    USE_PGVECTOR: bool = True
    
    # Combined Async Database URL
    DATABASE_URL: Optional[str] = None

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            # Enforce asyncpg driver
            url = self.DATABASE_URL
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://")
            return url
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # LLM Provider Configuration (ADR 009: Claude 3.5 Sonnet primary, GPT-4o fallback)
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # HuggingFace Configuration
    HUGGINGFACE_API_TOKEN: Optional[str] = None
    HUGGINGFACE_MODEL: str = "Qwen/Qwen2.5-Coder-32B-Instruct"

    # Integration Credentials
    GITHUB_WEBHOOK_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_SIGNING_SECRET: Optional[str] = None
    SLACK_CLIENT_ID: Optional[str] = None
    SLACK_CLIENT_SECRET: Optional[str] = None
    JIRA_BASE_URL: Optional[str] = None
    JIRA_EMAIL: Optional[str] = None
    JIRA_API_TOKEN: Optional[str] = None
    JIRA_CLIENT_ID: Optional[str] = None
    JIRA_CLIENT_SECRET: Optional[str] = None
    # Backup delta-sync poll interval, per system_architecture_design.md's Sync frequency
    # matrix ("Jira = webhook + 4-hour backup cron").
    JIRA_BACKUP_SYNC_INTERVAL_SECONDS: int = 14400
    # Calendar background poll interval, per implementation_roadmap.md Milestone 10's
    # documented "Background Jobs: Poller running every 15 minutes fetching updated meetings".
    CALENDAR_POLL_INTERVAL_SECONDS: int = 900
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None

    # Redis Configuration
    REDIS_HOST: str = "redis"
    REDIS_PORT: str = "6379"
    REDIS_URL: Optional[str] = None
    USE_REDIS: bool = True

    @property
    def redis_url_str(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
