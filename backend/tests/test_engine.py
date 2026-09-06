"""Unit tests for the workflow engine (no DB, no broker)."""

import pytest

from app.core.node import Node, RouterNode
from app.core.registry import register, workflow_for
from app.core.task_context import TaskContext
from app.core.workflow import Workflow


class Record(Node):
    """Appends its instance label to ctx.metadata['trail']."""

    def __init__(self, label: str) -> None:
        self.label = label

    @property
    def name(self) -> str:
        return self.label

    def process(self, ctx: TaskContext) -> TaskContext:
        ctx.metadata.setdefault("trail", []).append(self.label)
        ctx.nodes[self.name] = {"ok": True}
        return ctx


def test_workflow_runs_nodes_in_order(ctx):
    class W(Workflow):
        nodes = [Record("a"), Record("b"), Record("c")]

    W().run(ctx)
    assert ctx.metadata["trail"] == ["a", "b", "c"]
    assert set(ctx.nodes) == {"a", "b", "c"}


def test_router_jumps_to_named_node(ctx):
    class SkipToC(RouterNode):
        def route(self, _ctx):
            return "c"

    class W(Workflow):
        nodes = [Record("a"), SkipToC(), Record("b"), Record("c")]

    W().run(ctx)
    assert ctx.metadata["trail"] == ["a", "c"]  # b skipped


def test_router_none_continues_sequentially(ctx):
    class Continue(RouterNode):
        def route(self, _ctx):
            return None

    class W(Workflow):
        nodes = [Record("a"), Continue(), Record("b")]

    W().run(ctx)
    assert ctx.metadata["trail"] == ["a", "b"]


def test_router_unknown_target_raises(ctx):
    class Bad(RouterNode):
        def route(self, _ctx):
            return "missing"

    class W(Workflow):
        nodes = [Bad()]

    with pytest.raises(ValueError, match="unknown node"):
        W().run(ctx)


def test_registry_roundtrip():
    @register("test.registry_roundtrip")
    class W(Workflow):
        nodes = []

    assert workflow_for("test.registry_roundtrip") is W


def test_registry_unknown_type_raises():
    with pytest.raises(KeyError):
        workflow_for("test.never_registered")


def test_duplicate_registration_raises():
    @register("test.duplicate")
    class W1(Workflow):
        nodes = []

    with pytest.raises(ValueError, match="already registered"):

        @register("test.duplicate")
        class W2(Workflow):
            nodes = []


def test_to_result_is_json_safe(ctx):
    class Unserializable:
        def __str__(self) -> str:
            return "custom-object"

    ctx.nodes["a"] = {"count": 1}
    ctx.nodes["b"] = Unserializable()
    result = ctx.to_result()
    assert result["a"] == {"count": 1}
    assert result["b"] == "custom-object"
