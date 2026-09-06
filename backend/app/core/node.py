"""Nodes: the processing units a workflow executes.

A Node does one thing to the TaskContext and returns it. Store your output
in `ctx.nodes[self.name]` so downstream nodes and the event result can see
it. A RouterNode returns the *name* of the next node instead, letting a
workflow branch on data.
"""

from abc import ABC, abstractmethod

from app.core.task_context import TaskContext


class Node(ABC):
    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def process(self, ctx: TaskContext) -> TaskContext:
        """Do the work; mutate + return the context."""


class RouterNode(Node):
    """A node that picks the next node by name (conditional branching).

    `process` must call `self.route(ctx)` and store nothing itself.
    """

    def process(self, ctx: TaskContext) -> TaskContext:
        ctx.metadata["route"] = self.route(ctx)
        return ctx

    @abstractmethod
    def route(self, ctx: TaskContext) -> str | None:
        """Return the name of the node to jump to, or None to continue."""
