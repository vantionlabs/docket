"""Chat API: the streaming turn endpoint (AI-SDK v5 SSE wire format).

The request body follows the AI SDK's DefaultChatTransport shape: the
UI message list plus our custom `thread_id`. We take the last user
message as the question; history comes from the database (source of
truth), not from the client.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.schemas import NOT_FOUND, UNAUTHORIZED
from app.auth.access import require_thread_access
from app.auth.dependencies import CurrentUser
from app.chat.orchestrator import stream_turn
from app.chat.sse import STREAM_HEADERS
from app.db.engine import get_db
from app.security.ratelimit import chat_limiter

router = APIRouter(prefix="/chat", tags=["chat"], responses=UNAUTHORIZED)


class UIMessagePart(BaseModel):
    type: str
    text: str | None = None


class UIMessage(BaseModel):
    id: str | None = None
    role: str
    parts: list[UIMessagePart] = Field(default_factory=list)


class ChatRequest(BaseModel):
    thread_id: uuid.UUID
    messages: list[UIMessage] = Field(default_factory=list)


def _last_user_text(messages: list[UIMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            text = "".join(p.text or "" for p in message.parts if p.type == "text")
            if text.strip():
                return text.strip()
    return ""


@router.post(
    "/stream",
    summary="Stream a grounded chat turn (SSE)",
    description=(
        "Takes the last user message, runs retrieval + a grounded agent + "
        "citation validation, and streams the answer as AI-SDK v5 "
        "Server-Sent Events (`text/event-stream`). The turn is persisted only "
        "after its citations validate."
    ),
    responses={
        **NOT_FOUND,
        200: {
            "content": {"text/event-stream": {}},
            "description": "AI-SDK v5 UI message stream",
        },
        422: {"description": "No user message in the request"},
        429: {"description": "Rate limit exceeded"},
    },
)
def chat_stream(
    body: ChatRequest,
    user: CurrentUser = Depends(chat_limiter),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    thread = require_thread_access(db, body.thread_id, user.id)
    question = _last_user_text(body.messages)
    if not question:
        raise HTTPException(422, "No user message found in request")

    return StreamingResponse(
        stream_turn(db, thread, user.id, question),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
