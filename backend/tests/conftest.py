"""Shared fixtures.

The fast lane (`pytest -m "not integration"`) must run offline: no
database, no Redis, no OpenAI. Tests that need live services are marked
`@pytest.mark.integration` and read DATABASE_URL from the environment.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.task_context import TaskContext


@pytest.fixture
def ctx() -> TaskContext:
    """A TaskContext with a mocked DB session, for engine unit tests."""
    return TaskContext(
        event_id=uuid.uuid4(),
        event_type="test.event",
        payload={},
        user_id="user_test",
        db=MagicMock(),
    )
