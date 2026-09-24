import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import config

# Validated set for Document.status. The DB column is a plain String, not a
# Postgres ENUM (see app/db/models.py) because ENUMs need a migration to add
# a value and Alembic autogenerate handles them poorly — this Literal is
# where the set is actually enforced.
DocumentStatus = Literal["pending", "parsing", "chunking", "embedding", "ready", "failed"]

# MIME types for the file types this app can ingest: PDF, DOCX, TXT/MD, CSV/XLSX.
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "text/plain",  # .txt
    "text/markdown",  # .md
    "text/csv",  # .csv
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
}


class DocumentBase(BaseModel):
    filename: str = Field(min_length=4, max_length=100)
    content_type: str
    size_bytes: int


class DocumentCreate(DocumentBase):
    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        if value not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"Unsupported content type: {value}")
        return value

    @field_validator("size_bytes")
    @classmethod
    def validate_size_bytes(cls, value: int) -> int:
        if value < 0:
            raise ValueError(f"Invalid size bytes: {value}")
        if value > config.max_upload_bytes:
            raise ValueError(f"File size cannot be larger than: {config.max_upload_bytes}")
        return value


class DocumentRead(DocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: DocumentStatus
    error: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class IngestionStatusRead(BaseModel):
    """Lean response for GET /documents/{id}/status: just enough for a
    client to poll ingestion progress without the full document payload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: DocumentStatus
    error: str | None
    chunk_count: int
