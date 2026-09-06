"""App-layer ownership checks (this template has no RLS by design).

Every user-scoped resource is guarded by one of these helpers. They raise
404 (not 403) for rows owned by someone else, so the API never leaks
whether a foreign resource exists.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import ChatThread, Decision, SourceDocument


def require_thread_access(db: Session, thread_id: uuid.UUID, user_id: uuid.UUID) -> ChatThread:
    thread = db.get(ChatThread, thread_id)
    if thread is None or thread.user_id != user_id:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


def require_document_access(
    db: Session, document_id: uuid.UUID, user_id: uuid.UUID
) -> SourceDocument:
    doc = db.get(SourceDocument, document_id)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def require_decision_access(db: Session, decision_id: uuid.UUID, user_id: uuid.UUID) -> Decision:
    decision = db.get(Decision, decision_id)
    if decision is None or decision.user_id != user_id:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision
