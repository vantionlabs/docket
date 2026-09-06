"""The adapter surface (spec section 10).

A plugin surface, not a marketplace: one adapter per client, chosen by
config. `DryRunAdapter` is the default and it is what demos run on, which
is what makes it safe to show this to a prospect with their own documents
loaded.

Adapters are called from the execute workflow, which retries. An adapter
may therefore be invoked more than once for the same decision, so the
caller writes an `executions` row with a unique key BEFORE the outbound
call and refuses to make a second one. Adapters do not have to be
idempotent themselves; the row is what guarantees it.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.logging import get_logger

log = get_logger(__name__)


@dataclass
class AdapterRequest:
    """What the adapter is being asked to do, and enough context to do it."""

    decision_id: uuid.UUID
    action: str
    """The approved action, e.g. `approve_for_payment` or `reject`."""
    supplier: str
    reference: str
    """The document's own identifier, e.g. an invoice number."""
    amount: str
    currency: str
    assignee_hint: str | None = None
    note: str | None = None
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "decision_id": str(self.decision_id),
            "action": self.action,
            "supplier": self.supplier,
            "reference": self.reference,
            "amount": self.amount,
            "currency": self.currency,
            "assignee_hint": self.assignee_hint,
            "note": self.note,
            **({"extra": self.extra} if self.extra else {}),
        }


@dataclass
class AdapterResponse:
    ok: bool
    external_reference: str
    """What the target system called it. The audit trail's other half."""
    detail: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "ok": self.ok,
            "external_reference": self.external_reference,
            "detail": self.detail,
        }


class Adapter(Protocol):
    name: str

    def execute(self, request: AdapterRequest) -> AdapterResponse: ...


class DryRunAdapter:
    """Logs the instruction and returns a fake reference. Changes nothing.

    The default, deliberately. An adapter that cannot move money is the
    only kind you can point at a real client's invoices during a sales
    conversation.
    """

    name = "dry_run"

    def execute(self, request: AdapterRequest) -> AdapterResponse:
        log.info(
            "adapter.dry_run",
            decision_id=str(request.decision_id),
            action=request.action,
            supplier=request.supplier,
            reference=request.reference,
            amount=f"{request.amount} {request.currency}",
        )
        return AdapterResponse(
            ok=True,
            external_reference=f"dry-run-{request.decision_id}",
            detail={"note": "No system of record was contacted. Nothing was paid."},
        )


_ADAPTERS: dict[str, Adapter] = {}


def register_adapter(adapter: Adapter) -> Adapter:
    if adapter.name in _ADAPTERS:
        raise ValueError(f"adapter already registered under {adapter.name!r}")
    _ADAPTERS[adapter.name] = adapter
    return adapter


def get_adapter(name: str | None = None) -> Adapter:
    """The configured adapter, or the dry run when nothing is configured.

    Falling back to dry run rather than raising is deliberate: a
    misconfigured deployment should do nothing, not guess which real
    system to call.
    """
    from app.config import settings

    wanted = name or settings.execution_adapter
    adapter = _ADAPTERS.get(wanted)
    if adapter is None:
        log.warning("adapter.unknown", requested=wanted, falling_back_to="dry_run")
        return _ADAPTERS["dry_run"]
    return adapter


register_adapter(DryRunAdapter())
