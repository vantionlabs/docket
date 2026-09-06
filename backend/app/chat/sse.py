"""AI-SDK v5 SSE wire format.

The frontend's `useChat` (DefaultChatTransport) consumes a UI message
stream: newline-delimited `data: {json}` frames, custom parts prefixed
`data-`, a terminal `data: [DONE]`, and the marker header
`x-vercel-ai-ui-message-stream: v1`. Frame shapes must match exactly or
the UI silently renders nothing — all frames are built HERE and nowhere
else, and tests pin the format.
"""

import json
import uuid
from typing import Any

STREAM_HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}


def _frame(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def start(message_id: str | None = None) -> str:
    return _frame({"type": "start", "messageId": message_id or str(uuid.uuid4())})


def text_start(text_id: str) -> str:
    return _frame({"type": "text-start", "id": text_id})


def text_delta(text_id: str, delta: str) -> str:
    return _frame({"type": "text-delta", "id": text_id, "delta": delta})


def text_end(text_id: str) -> str:
    return _frame({"type": "text-end", "id": text_id})


def data_part(name: str, data: Any) -> str:
    """Custom part; `name` must not include the `data-` prefix."""
    return _frame({"type": f"data-{name}", "data": data})


def error(message: str) -> str:
    return _frame({"type": "error", "errorText": message})


def finish() -> str:
    return _frame({"type": "finish"})


def done() -> str:
    return "data: [DONE]\n\n"
