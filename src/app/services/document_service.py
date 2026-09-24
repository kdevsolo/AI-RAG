import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import config
from app.db.models import Document
from app.schema.document import DocumentCreate


class DocumentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def upload_document(self, user_id: uuid.UUID, file: UploadFile) -> Document:
        content = await file.read()

        try:
            DocumentCreate(
                filename=file.filename or "",
                content_type=file.content_type or "",
                size_bytes=len(content),
            )
        except ValidationError as exc:
            # Raised here, not left to propagate: an uncaught pydantic
            # ValidationError from inside a service has no FastAPI handler
            # registered for it and surfaces as a bare 500, not a useful
            # 422. HTTPException is the boundary this codebase's services
            # translate validation failures into (see UserService.login).
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        doc_id = uuid.uuid4()
        dest = config.upload_dir / str(user_id) / f"{doc_id}{Path(file.filename or '').suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

        document = Document(
            id=doc_id,
            user_id=user_id,
            filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(content),
            storage_path=str(dest),
            sha256=hashlib.sha256(content).hexdigest(),
            status="pending",
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    async def get_all_documents(self, user_id: uuid.UUID) -> list[Document]:
        return self.db.query(Document).filter(Document.user_id == user_id).all()

    def get_for_user(self, document_id: uuid.UUID, user_id: uuid.UUID) -> Document | None:
        # Filters on both id AND user_id in one query, rather than fetching
        # by id and checking ownership after: a document that exists but
        # belongs to someone else must look identical to one that doesn't
        # exist at all (404, never 403 — don't confirm existence).
        return (
            self.db.query(Document)
            .filter(Document.id == document_id, Document.user_id == user_id)
            .first()
        )

    def delete_for_user(self, document_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        document = self.get_for_user(document_id, user_id)
        if document is None:
            return False

        storage_path = Path(document.storage_path)
        # DB row is the source of truth; a missing file on disk must not
        # block deleting the row (e.g. it was already cleaned up once).
        storage_path.unlink(missing_ok=True)

        self.db.delete(document)
        self.db.commit()
        return True
