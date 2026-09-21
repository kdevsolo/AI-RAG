import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# A module-level literal, NOT config.openai_embedding_dimensions: Alembic renders
# this into migration files, and a migration whose schema depends on a runtime
# env var is not reproducible.
EMBEDDING_DIM = 1536


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(30))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password: Mapped[str] = mapped_column()

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r})"


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 hex of the token, never the token itself: a leaked dump must
    # not yield usable credentials.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"RefreshToken(id={self.id!r}, user_id={self.user_id!r})"


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int] = mapped_column()
    storage_path: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64), index=True)

    # DocumentStatus Literal in app/schema/document.py is the validated set;
    # kept a plain String here (not a Postgres ENUM) because ENUMs need a
    # migration to add a value and Alembic autogenerate handles them poorly.
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    chunk_count: Mapped[int] = mapped_column(default=0)
    # Correlates the row with its Temporal run for diagnostics; unset until
    # the upload endpoint starts the workflow.
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    def __repr__(self) -> str:
        return f"Document(id={self.id!r}, user_id={self.user_id!r})"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    # Denormalised from documents.user_id: retrieval filters on this column
    # directly, so it can combine with the HNSW index. Filtering via a join
    # to documents would defeat the index.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(default=0)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIM))

    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"
        ),
    )

    def __repr__(self) -> str:
        return f"DocumentChunk(id={self.id!r}, document_id={self.document_id!r})"


class ChatThread(Base, TimestampMixin):
    __tablename__ = "chat_threads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Nullable: a thread exists before it has a title (none assigned yet by
    # the user or the model).
    title: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    # Nullable: unset until the first message lands: a brand-new thread has
    # no messages yet, so there is no valid value to insert at creation.
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"ChatThread(id={self.id!r}, user_id={self.user_id!r})"
