"""Threads API: chat history for the sidebar + thread restore."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import NOT_FOUND, UNAUTHORIZED, MessageOut, ThreadOut
from app.auth.access import require_thread_access
from app.auth.dependencies import CurrentUser, get_current_user
from app.db.engine import get_db
from app.db.models import ChatMessage, ChatThread

router = APIRouter(prefix="/threads", tags=["threads"], responses=UNAUTHORIZED)


@router.get("", response_model=list[ThreadOut], summary="List your chat threads")
def list_threads(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatThread]:
    return list(
        db.scalars(
            select(ChatThread)
            .where(ChatThread.user_id == user.id)
            .order_by(ChatThread.updated_at.desc())
        )
    )


@router.post("", response_model=ThreadOut, status_code=201, summary="Create a thread")
def create_thread(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatThread:
    thread = ChatThread(user_id=user.id)
    db.add(thread)
    db.commit()
    return thread


@router.get(
    "/{thread_id}/messages",
    response_model=list[MessageOut],
    summary="Thread message history",
    description="Persisted turns with their citations, in order — used to restore a thread.",
    responses=NOT_FOUND,
)
def get_messages(
    thread_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatMessage]:
    require_thread_access(db, thread_id, user.id)
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .options(selectinload(ChatMessage.citations))
            .order_by(ChatMessage.sequence)
        )
    )


@router.delete(
    "/{thread_id}", status_code=204, summary="Delete a thread", responses=NOT_FOUND
)
def delete_thread(
    thread_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    thread = require_thread_access(db, thread_id, user.id)
    db.delete(thread)
    db.commit()
