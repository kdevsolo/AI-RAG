import uuid
from dataclasses import dataclass
from pathlib import Path

from langchain_openai import OpenAIEmbeddings
from temporalio import activity

from app.core.config import config
from app.db.models import Document, DocumentChunk
from app.db.session import SessionLocal
from app.rag.chunking import split
from app.rag.parsers import extract_text
from app.temporal.shared import IngestDocumentInput, MarkFailedInput

# extract_text() switches on the short type key, but Document.content_type
# stores the full MIME type (see app/schema/document.py ALLOWED_CONTENT_TYPES) —
# this is the mapping between the two.
_CONTENT_TYPE_TO_PARSER_KEY = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}

# Chunks are batched to OpenAI's embeddings endpoint rather than embedded one
# at a time: far fewer round-trips for a large document. activity.heartbeat()
# fires after each batch so a hung worker is detected in ~heartbeat_timeout,
# not after the full start_to_close_timeout.
_EMBED_BATCH_SIZE = 64


@dataclass
class ChunkAndStoreInput:
    document_id: str
    text: str


@dataclass
class EmbedChunksInput:
    document_id: str


def _parser_key(content_type: str) -> str:
    from app.rag.parsers import UnsupportedFileTypeError

    try:
        return _CONTENT_TYPE_TO_PARSER_KEY[content_type]
    except KeyError:
        raise UnsupportedFileTypeError(f"Unknown document type: {content_type}") from None


@activity.defn
def parse_document(inp: IngestDocumentInput) -> str:
    """Extract plain text from the uploaded file. Returns the text directly —
    it is the *return value of this activity*, not something that crosses the
    workflow boundary again: the workflow passes it straight into the next
    activity's input without holding or re-emitting it itself."""
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(inp.document_id))
        if document is None:
            raise ValueError(f"Document not found: {inp.document_id}")

        document.status = "parsing"
        db.commit()

        parser_key = _parser_key(document.content_type)
        text = extract_text(Path(inp.file_path), parser_key)
        return text
    finally:
        db.close()


@activity.defn
def chunk_and_store(inp: ChunkAndStoreInput) -> int:
    """Split text into chunks and persist them. Idempotent: deletes any
    existing chunks for this document first, so a retry after a
    successful-but-unacknowledged run doesn't duplicate rows (the unique
    constraint on (document_id, chunk_index) is the backstop)."""
    db = SessionLocal()
    try:
        document_id = uuid.UUID(inp.document_id)
        document = db.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document not found: {inp.document_id}")

        document.status = "chunking"
        db.commit()

        pieces = split(inp.text, config.chunk_size, config.chunk_overlap)

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        for index, piece in enumerate(pieces):
            db.add(
                DocumentChunk(
                    document_id=document_id,
                    user_id=document.user_id,
                    chunk_index=index,
                    content=piece,
                    token_count=len(piece) // 4,  # rough estimate, not exact tokenization
                    embedding=[0.0]
                    * config.openai_embedding_dimensions,  # placeholder until embed_chunks
                )
            )
        db.commit()
        return len(pieces)
    finally:
        db.close()


@activity.defn
def embed_chunks(inp: EmbedChunksInput) -> int:
    """Embed every chunk for this document via OpenAI, batched. Idempotent:
    re-embeds and overwrites rather than appending, so a retry is safe."""
    db = SessionLocal()
    try:
        document_id = uuid.UUID(inp.document_id)
        document = db.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document not found: {inp.document_id}")

        document.status = "embedding"
        db.commit()

        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        embeddings = OpenAIEmbeddings(
            openai_api_key=config.openai_api_key,
            model=config.openai_embedding_model,
            dimensions=config.openai_embedding_dimensions,
        )
        for batch_start in range(0, len(chunks), _EMBED_BATCH_SIZE):
            batch = chunks[batch_start : batch_start + _EMBED_BATCH_SIZE]
            vectors = embeddings.embed_documents([chunk.content for chunk in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding = vector
            db.commit()
            activity.heartbeat(batch_start)

        return len(chunks)
    finally:
        db.close()


@activity.defn
def mark_ready(document_id: str) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            raise ValueError(f"Document not found: {document_id}")

        chunk_count = (
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).count()
        )
        document.status = "ready"
        document.chunk_count = chunk_count
        document.error = None
        db.commit()
    finally:
        db.close()


@activity.defn
def mark_failed(inp: MarkFailedInput) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(inp.document_id))
        if document is None:
            raise ValueError(f"Document not found: {inp.document_id}")

        document.status = "failed"
        document.error = inp.error
        db.commit()
    finally:
        db.close()
