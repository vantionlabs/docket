"""Documents API: presigned R2 upload, ingestion trigger, listing.

Upload flow:
  1. POST /documents/presign  -> row (pending_upload) + presigned PUT URL
  2. browser PUTs the file directly to R2 (exact same Content-Type)
  3. POST /documents/{id}/confirm -> status uploaded + document.ingest event
  4. worker workflow: processing -> ready/failed; frontend polls GET /documents
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    NOT_FOUND,
    UNAUTHORIZED,
    DocumentOut,
    PresignRequest,
    PresignResponse,
)
from app.auth.access import require_document_access
from app.auth.dependencies import CurrentUser, get_current_user
from app.db.engine import get_db
from app.db.models import DocumentStatus, Event, SourceDocument
from app.storage.r2 import delete_object, object_key, presign_put
from app.worker.tasks import dispatch_event

router = APIRouter(prefix="/documents", tags=["documents"], responses=UNAUTHORIZED)


@router.post(
    "/presign",
    response_model=PresignResponse,
    summary="Start an upload",
    description=(
        "Creates a `pending_upload` document row and returns a presigned R2 "
        "PUT URL. The browser then PUTs the file to that URL with the exact "
        "`content_type` given here, and calls confirm."
    ),
)
def presign_upload(
    body: PresignRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PresignResponse:
    key = object_key(user.id, body.filename)
    doc = SourceDocument(
        user_id=user.id,
        org_id=user.org_id,
        # Defaults to transactional: a document nobody classified must not
        # become policy by accident (spec section 8).
        collection=body.collection,
        filename=body.filename,
        r2_key=key,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        status=DocumentStatus.pending_upload,
    )
    db.add(doc)
    db.commit()
    return PresignResponse(
        document_id=doc.id,
        key=key,
        upload_url=presign_put(key, body.content_type),
    )


@router.post(
    "/{document_id}/confirm",
    response_model=DocumentOut,
    status_code=202,
    summary="Confirm an upload and start ingestion",
    description=(
        "Marks the document `uploaded` and emits a `document.ingest` event. "
        "A worker then chunks and embeds it; poll `GET /documents` for status "
        "(`processing` → `ready`/`failed`)."
    ),
    responses=NOT_FOUND,
)
def confirm_upload(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourceDocument:
    doc = require_document_access(db, document_id, user.id)
    doc.status = DocumentStatus.uploaded
    event = Event(
        user_id=user.id,
        type="document.ingest",
        payload={"document_id": str(doc.id)},
    )
    db.add(event)
    db.commit()
    dispatch_event(event.id)
    return doc


@router.get(
    "",
    response_model=list[DocumentOut],
    summary="List your documents",
    description="Newest first, with ingestion `status`. Poll this while a document is processing.",
)
def list_documents(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SourceDocument]:
    return list(
        db.scalars(
            select(SourceDocument)
            .where(SourceDocument.user_id == user.id)
            .order_by(SourceDocument.created_at.desc())
        )
    )


@router.delete(
    "/{document_id}",
    status_code=204,
    summary="Delete a document",
    description="Removes the R2 object and the row; its chunks and citations cascade.",
    responses=NOT_FOUND,
)
def delete_document(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    doc = require_document_access(db, document_id, user.id)
    delete_object(doc.r2_key)
    db.delete(doc)  # chunks + citations cascade
    db.commit()
