import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.api.deps import CurrentUser
from app.db.deps import DbSession
from app.schema.document import DocumentRead, IngestionStatusRead
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


# dependency injection
def get_document_service(db: DbSession) -> DocumentService:
    return DocumentService(db)


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]


# routes
@router.post("", status_code=202, response_model=DocumentRead)
async def upload_document(
    user: CurrentUser,
    service: DocumentServiceDep,
    file: Annotated[UploadFile, File()],
):
    return await service.upload_document(user.id, file)


@router.get("", response_model=list[DocumentRead])
async def get_all_documents(user: CurrentUser, service: DocumentServiceDep):
    return await service.get_all_documents(user.id)


# Declared before /{document_id}: FastAPI matches in order, so the dynamic
# route would otherwise try to parse "status" fragments of other paths as
# an id. Not an issue here since /{document_id}/status is a suffix, but
# kept for the same reason /me precedes /{user_id} in user_routes.py.
@router.get("/{document_id}", status_code=200, response_model=DocumentRead)
def get_document(document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep):
    document = service.get_for_user(document_id, user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found!")
    return document


@router.get("/{document_id}/status", status_code=200, response_model=IngestionStatusRead)
def get_document_status(document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep):
    document = service.get_for_user(document_id, user.id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found!")
    return document


@router.delete("/{document_id}", status_code=204, response_class=Response)
def delete_document(document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep) -> None:
    deleted = service.delete_for_user(document_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="document not found!")
