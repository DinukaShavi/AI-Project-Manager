import re
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import DateTime, Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, declared_attr
import uuid

# Base class mapping helper
class CustomBase:
    # Auto-generate __tablename__ in snake_case
    @declared_attr
    def __tablename__(cls) -> str:
        name = cls.__name__
        # CamelCase to snake_case
        return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

    # Default Primary Key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Standard Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

# Soft Delete mixin class
class SoftDeleteMixin:
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

# SQLAlchemy base model object
Base = declarative_base(cls=CustomBase)

# Dynamic Vector Compilation Fallback if pgvector database extension is not present
from sqlalchemy.ext.compiler import compiles
from app.core.config import settings
try:
    from pgvector.sqlalchemy import Vector
    if not settings.USE_PGVECTOR:
        @compiles(Vector, 'postgresql')
        def compile_vector(element, compiler, **kw):
            return "DOUBLE PRECISION[]"
        
        # Override processors to act as identity functions for standard ARRAY(Float) compat
        Vector.bind_processor = lambda self, dialect: lambda value: value
        Vector.result_processor = lambda self, dialect, coltype: lambda value: value
except ImportError:
    pass

