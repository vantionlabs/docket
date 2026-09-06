"""Workflow: an ordered sequence of nodes with optional routing.

Execution walks `nodes` in order. When a RouterNode sets a route, execution
jumps to the node with that name (skipping forward or backward); a route of
None continues sequentially. Exceptions propagate to the worker, which marks
the event failed — nodes should not swallow errors they can't handle.
"""

from app.core.node import Node, RouterNode
from app.core.task_context import TaskContext
from app.logging import get_logger

log = get_logger(__name__)


class Workflow:
    """Subclass and set `nodes` (instances, in execution order)."""

    nodes: list[Node] = []

    def on_failure(self, ctx: TaskContext, exc: Exception) -> None:
        """Domain cleanup when any node raises (e.g. flip a status row to
        failed). Runs with a fresh transaction after rollback; the event row
        itself is marked failed by the worker. Default: nothing."""

    def run(self, ctx: TaskContext) -> TaskContext:
        index = {node.name: i for i, node in enumerate(self.nodes)}
        i = 0
        while i < len(self.nodes):
            node = self.nodes[i]
            log.info("workflow.node.start", workflow=type(self).__name__, node=node.name)
            ctx = node.process(ctx)
            log.info("workflow.node.done", workflow=type(self).__name__, node=node.name)

            if isinstance(node, RouterNode):
                target = ctx.metadata.pop("route", None)
                if target is not None:
                    if target not in index:
                        raise ValueError(
                            f"{type(self).__name__}: router {node.name} "
                            f"routed to unknown node {target!r}"
                        )
                    i = index[target]
                    continue
            i += 1
        return ctx
