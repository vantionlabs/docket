"""Chat turn orchestration.

One turn = status events -> agent run (in a worker thread) -> grounding
validation (retry once) -> stream the validated answer word-by-word ->
persist. Fail-closed: if validation keeps failing, the user gets an
honest "couldn't verify" message and nothing is persisted as fact.
"""

import asyncio
import re
import uuid
from collections.abc import AsyncGenerator

from sqlalchemy.orm import Session

from app.agent.agent import run_turn
from app.agent.deps import AgentDeps
from app.chat import sse
from app.chat.persistence import load_history, persist_turn
from app.db.models import ChatThread
from app.grounding.turn_registry import TurnRegistry
from app.grounding.validator import validate
from app.logging import get_logger

log = get_logger(__name__)

MAX_VALIDATION_ATTEMPTS = 2

INSUFFICIENT_MESSAGE = (
    "I couldn't find enough support for this in your documents, so I'd rather "
    "not guess. Try rephrasing the question, or upload documents that cover it."
)
UNVERIFIED_MESSAGE = (
    "I generated an answer but couldn't verify its citations against your "
    "documents, so I'm not showing it. Please try asking again."
)


async def stream_turn(
    db: Session,
    thread: ChatThread,
    user_id: uuid.UUID,
    question: str,
) -> AsyncGenerator[str, None]:
    yield sse.start()
    yield sse.data_part("status", {"stage": "analyzing"})

    history = load_history(db, thread.id)

    answer_text: str | None = None
    citations = []
    for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
        registry = TurnRegistry()
        deps = AgentDeps(user_id=user_id, registry=registry)
        try:
            result = await asyncio.to_thread(run_turn, question, history, deps)
        except Exception:
            log.exception("chat.agent_failed", thread_id=str(thread.id))
            yield sse.error("The assistant failed to produce an answer. Please try again.")
            yield sse.done()
            return

        yield sse.data_part("status", {"stage": "verifying"})
        validation = await asyncio.to_thread(validate, result, registry, user_id)

        if validation.ok:
            citations = validation.citations or []
            answer_text = (
                INSUFFICIENT_MESSAGE if result.insufficient_evidence else result.answer
            )
            break

        log.warning(
            "chat.validation_failed",
            thread_id=str(thread.id),
            attempt=attempt,
            reason=validation.reason,
        )
        if attempt < MAX_VALIDATION_ATTEMPTS:
            yield sse.data_part("status", {"stage": "retrying"})

    if answer_text is None:
        answer_text = UNVERIFIED_MESSAGE
        citations = []

    # Stream the answer word-by-word, then citations as data parts.
    yield sse.data_part("status", {"stage": "streaming"})
    text_id = str(uuid.uuid4())
    yield sse.text_start(text_id)
    for word in re.split(r"(\s+)", answer_text):
        if word:
            yield sse.text_delta(text_id, word)
            await asyncio.sleep(0)  # let the event loop flush
    yield sse.text_end(text_id)

    for c in citations:
        yield sse.data_part(
            "citation",
            {
                "citation_index": c.index,
                "chunk_id": str(c.chunk_id),
                "document_id": str(c.document_id),
                "excerpt": c.excerpt,
                "filename": c.filename,
            },
        )

    await asyncio.to_thread(persist_turn, db, thread, question, answer_text, citations)

    yield sse.finish()
    yield sse.done()
