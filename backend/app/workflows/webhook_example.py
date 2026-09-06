"""Example webhook workflow.

Registered for `webhook.example`, so `POST /webhooks/example` (with a valid
signature) runs it. It just records the payload's shape — replace it with a
real workflow, and register more `webhook.<source>` workflows per provider.
"""

from app.core.node import Node
from app.core.registry import register
from app.core.task_context import TaskContext
from app.core.workflow import Workflow


class SummarizePayload(Node):
    def process(self, ctx: TaskContext) -> TaskContext:
        payload = ctx.payload or {}
        ctx.nodes[self.name] = {"keys": sorted(payload.keys()), "count": len(payload)}
        return ctx


@register("webhook.example")
class ExampleWebhookWorkflow(Workflow):
    nodes = [SummarizePayload()]
