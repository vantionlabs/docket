"""Documents API: presigned R2 upload, ingestion trigger, listing.

Upload flow:
  1. POST /documents/presign  -> row (pending_upload) + presigned PUT URL
  2. browser PUTs the file directly to R2 (exact same Content-Type)
  3. POST /documents/{id}/confirm -> status uploaded + document.ingest event
  4. worker workflow: processing -> ready/failed; frontend polls GET /documents
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    NOT_FOUND,
    UNAUTHORIZED,
    DocumentOut,
    DocumentPage,
    PresignRequest,
    PresignResponse,
)
from app.auth.access import require_document_access
from app.auth.dependencies import CurrentUser, get_current_user
from app.core.document_intake import receive_document
from app.db.engine import get_db
from app.db.models import Collection, DocumentStatus, SourceDocument
from app.storage.r2 import delete_object, object_key, presign_put

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
    summary="Confirm an upload and start work on the document",
    description=(
        "Marks the document `uploaded`, records an intake, and queues what "
        "the document is for.\n\n"
        "A `policy` document is chunked, embedded and indexed into the "
        "obligations coverage checking uses. A `transactional` document goes "
        "straight to the decision pipeline and appears in the review queue. "
        "Poll `GET /documents` for ingestion status, `GET /decisions` for the "
        "decision."
    ),
    responses=NOT_FOUND,
)
def confirm_upload(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourceDocument:
    doc = require_document_access(db, document_id, user.id)
    receive_document(db, doc, source="upload", external_ref=f"upload:{doc.id}")
    return doc


@router.get(
    "",
    response_model=DocumentPage,
    summary="List your documents",
    description=(
        "Newest first, with ingestion `status`. Paginated, and filterable by "
        "`collection` (`policy` for the rules, `transactional` for the "
        "documents judged against them) and by filename with `q`."
    ),
)
def list_documents(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    collection: Collection | None = Query(default=None),
    q: str | None = Query(default=None, description="Filename contains, case-insensitive."),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentPage:
    filters = [SourceDocument.user_id == user.id]
    if collection is not None:
        filters.append(SourceDocument.collection == collection)
    if q:
        filters.append(SourceDocument.filename.ilike(f"%{q}%"))

    total = db.scalar(
        select(func.count()).select_from(SourceDocument).where(*filters)
    ) or 0
    items = list(
        db.scalars(
            select(SourceDocument)
            .where(*filters)
            .order_by(SourceDocument.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return DocumentPage(
        items=[DocumentOut.model_validate(i, from_attributes=True) for i in items],
        total=total,
        limit=limit,
        offset=offset,
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
