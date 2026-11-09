"""
SQLAlchemy 2.0 Declarative Base and Common Mixins.

Provides:
- DeclarativeBase with standardized naming conventions for constraints.
- GUID and Timestamp mixins for PostgreSQL and SQLite test compatibility.
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import DateTime, MetaData, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit naming conventions for constraints to support deterministic Alembic migrations
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative Base class for all EdgeMind PostgreSQL models."""
    metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Standard timestamp mixin with timezone-aware UTC datetimes."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

