"""Chat persistence: threads, messages, citations.

Messages are persisted only AFTER a turn's answer has passed grounding
validation — a failed turn leaves no partial assistant message behind.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, ChatThread, MessageCitation
from app.grounding.validator import ValidatedCitation


def next_sequence(db: Session, thread_id: uuid.UUID) -> int:
    current = db.scalar(
        select(func.max(ChatMessage.sequence)).where(ChatMessage.thread_id == thread_id)
    )
    return (current or 0) + 1


def load_history(db: Session, thread_id: uuid.UUID) -> list[dict]:
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.sequence)
    )
    return [{"role": m.role, "content": m.content} for m in messages]


def persist_turn(
    db: Session,
    thread: ChatThread,
    question: str,
    answer: str,
    citations: list[ValidatedCitation],
) -> ChatMessage:
    seq = next_sequence(db, thread.id)
    user_message = ChatMessage(
        thread_id=thread.id, role="user", content=question, sequence=seq
    )
    assistant_message = ChatMessage(
        thread_id=thread.id, role="assistant", content=answer, sequence=seq + 1
    )
    db.add_all([user_message, assistant_message])
    db.flush()

    db.add_all(
        MessageCitation(
            message_id=assistant_message.id,
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            citation_index=c.index,
            excerpt=c.excerpt,
            filename=c.filename,
        )
        for c in citations
    )

    # First turn titles the thread from the question.
    if seq == 1:
        thread.title = question[:80]

    db.commit()
    return assistant_message
