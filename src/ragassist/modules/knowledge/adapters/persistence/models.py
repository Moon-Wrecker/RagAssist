"""SQLAlchemy persistence models for Knowledge module."""

from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PG_UUID
from ragassist.shared.db.models import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy.types import UserDefinedType

    class Vector(UserDefinedType):  # type: ignore[no-redef]
        """Fallback Vector type when pgvector package is not installed."""

        def __init__(self, dim: int = 1536) -> None:
            self.dim = dim

        def get_col_spec(self, **kw: object) -> str:
            return f"vector({self.dim})"


class ChunkModel(Base):
    """Database model for document chunks and vector embeddings."""

    __tablename__ = "chunks"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid4()))
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    document_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    text = Column(Text, nullable=False)
    embed_text = Column(Text, nullable=True)
    heading_path = Column(JSONB, nullable=True, default=list)
    page = Column(Integer, nullable=True)
    title = Column(String(255), nullable=True, default="")
    embedding = Column(Vector(1536), nullable=True)
    fts = Column(TSVECTOR, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
