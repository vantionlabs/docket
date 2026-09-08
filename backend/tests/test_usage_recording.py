"""Usage recording, which silently did nothing for the whole build.

`result.usage` is a property in current pydantic-ai, not a method. Six call
sites wrote `result.usage()`, which raises TypeError, and every one of them
wrapped it in `except Exception: pass`. No Anthropic call in this project
ever logged a token. Nothing failed; the spend log was just empty and
looked like a project that had not run yet.

Worse, in `contextualize` the accounting sat inside the same try as the LLM
call, so the TypeError discarded a successful generation and the llm
strategy fell back to structural every single time.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.observability.usage import record_run_usage


class _PropertyUsage:
    """Current pydantic-ai: usage is a property."""

    usage = SimpleNamespace(input_tokens=1000, output_tokens=200)


class _MethodUsage:
    """Older pydantic-ai: usage was a method."""

    def usage(self):
        return SimpleNamespace(input_tokens=1000, output_tokens=200)


class _LegacyNames:
    """Older still: request_tokens / response_tokens."""

    usage = SimpleNamespace(request_tokens=1000, response_tokens=200)


@pytest.mark.parametrize("result", [_PropertyUsage(), _MethodUsage(), _LegacyNames()])
def test_every_sdk_shape_records(result):
    with patch("app.observability.usage.record_usage") as recorded:
        record_run_usage(result, operation="chat", model="claude-sonnet-5")
    recorded.assert_called_once()
    assert recorded.call_args.kwargs["input_tokens"] == 1000
    assert recorded.call_args.kwargs["output_tokens"] == 200


def test_the_property_shape_is_the_one_that_was_broken():
    """The regression test proper: `result.usage()` on this object raises
    TypeError, which is exactly what every call site used to do."""
    with pytest.raises(TypeError):
        _PropertyUsage().usage()


def test_a_result_with_no_usage_logs_rather_than_passing_silently():
    """The swallow is what hid this for the whole build. It may not raise,
    but it must leave a trace."""
    with patch("app.observability.usage.log") as logger:
        record_run_usage(object(), operation="chat", model="claude-sonnet-5")
    logger.exception.assert_called_once()


def test_recording_never_raises_into_the_caller():
    record_run_usage(None, operation="chat", model="claude-sonnet-5")


def test_the_operation_and_model_are_passed_through():
    with patch("app.observability.usage.record_usage") as recorded:
        record_run_usage(
            _PropertyUsage(), operation="decision", model="claude-haiku-4-5"
        )
    assert recorded.call_args.kwargs["operation"] == "decision"
    assert recorded.call_args.kwargs["model"] == "claude-haiku-4-5"
