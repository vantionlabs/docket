"""Pin the AI-SDK v5 SSE wire format — a mismatch renders nothing in the UI."""

import json

from app.chat import sse


def parse(frame: str) -> dict:
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    return json.loads(frame[len("data: ") : -2])


def test_start_frame():
    payload = parse(sse.start("msg-1"))
    assert payload == {"type": "start", "messageId": "msg-1"}


def test_text_frames():
    assert parse(sse.text_start("t1")) == {"type": "text-start", "id": "t1"}
    assert parse(sse.text_delta("t1", "hello ")) == {
        "type": "text-delta",
        "id": "t1",
        "delta": "hello ",
    }
    assert parse(sse.text_end("t1")) == {"type": "text-end", "id": "t1"}


def test_data_part_is_prefixed():
    payload = parse(sse.data_part("citation", {"citation_index": 1}))
    assert payload["type"] == "data-citation"
    assert payload["data"] == {"citation_index": 1}


def test_error_frame():
    assert parse(sse.error("boom")) == {"type": "error", "errorText": "boom"}


def test_finish_and_done():
    assert parse(sse.finish()) == {"type": "finish"}
    assert sse.done() == "data: [DONE]\n\n"


def test_stream_headers_marker():
    assert sse.STREAM_HEADERS["x-vercel-ai-ui-message-stream"] == "v1"
