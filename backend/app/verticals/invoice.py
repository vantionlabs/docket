"""Supplier invoices: the first vertical, moved out of the pipeline.

Everything here used to live in decide.py, coverage.py and rails.py. It is
not better code for having moved; it is in the right place, which is what
makes a second vertical possible without editing the pipeline.
"""

import re
from decimal import Decimal

from app.extraction.schemas.invoice import SCHEMA_NAME, Invoice
from app.verticals.base import DeterministicChecks, warnings_block

_WORD = re.compile(r"[a-z0-9]+")


class InvoiceVertical:
    name = SCHEMA_NAME
    schema = Invoice

    dimensions = frozenset(
        {
            "amount",  # thresholds and approval bands
            "purchase_order",
            "supplier",
            "currency",
            "vat",
            "payment_terms",
            "duplicate",
            "scope",  # what the policy covers at all
            "escalation",  # what to do when it does not settle a case
        }
    )

    def check(self, document: Invoice) -> DeterministicChecks:
        from app.extraction.arithmetic import check_invoice

        report = check_invoice(document)
        return DeterministicChecks(ok=report.ok, failures=report.failures)

    def query(self, document: Invoice) -> str:
        """The policy question this invoice asks, in the corpus's own words.

        Names the *dimensions* policy cares about, not only the values on
        the invoice. The M1 spike found out why: a USD invoice whose query
        said "amount 8400 USD" never retrieved the currency clause, because
        the clause says "euro" and "another currency" and the invoice says
        neither. A missed clause is an unasked question, and an unasked
        question looks exactly like a satisfied one.
        """
        parts = [
            f"supplier {document.supplier.value}",
            f"amount {document.total_incl_vat.value} {document.currency.value}",
            "purchase order" if document.po_number else "no purchase order number supplied",
        ]
        if document.cost_centre is not None:
            parts.append(f"cost centre {document.cost_centre.value}")
        if document.line_items:
            parts.extend(item.description.value for item in document.line_items[:5])

        if document.currency.value.strip().upper() != "EUR":
            parts.append("invoice presented in another currency, not payable in euro")
        if document.due_on is not None:
            days = (document.due_on.value - document.issued_on.value).days
            if days < 14:
                parts.append(f"shortened payment terms, payment demanded in {days} days")

        parts.append(
            "spend threshold approval authority, approved supplier list, purchase order "
            "requirement, payment terms, currency, VAT rate, duplicate invoice"
        )
        return ", ".join(parts)

    def render(
        self, document: Invoice, checks: DeterministicChecks, unverified: list[str]
    ) -> str:
        lines = [
            "INVOICE (extracted):",
            f"  supplier: {document.supplier.value}",
            f"  invoice number: {document.invoice_number.value}",
            f"  issued: {document.issued_on.value}",
            f"  currency: {document.currency.value}",
            f"  total incl VAT: {document.total_incl_vat.value}",
            f"  VAT: {document.vat_amount.value}",
            f"  subtotal excl VAT: {document.subtotal_excl_vat}",
            f"  PO number: {document.po_number.value if document.po_number else 'none'}",
            f"  cost centre: "
            f"{document.cost_centre.value if document.cost_centre else 'none'}",
        ]
        if document.line_items:
            lines.append("  line items:")
            lines.extend(
                f"    - {item.description.value}: {item.quantity.value} x "
                f"{item.unit_price.value} = {item.amount.value}"
                for item in document.line_items
            )
        return "\n".join(lines + warnings_block(checks, unverified))

    def triggers(self, document: Invoice, checks: DeterministicChecks) -> set[str]:
        """Which dimensions this invoice puts in play.

        Deliberately generous. A dimension costs one clause in the prompt if
        it turns out not to matter, and costs a missed rule if it is left
        out. `scope` and `escalation` are absent because their obligations
        carry `always_applies`.
        """
        triggered = {"amount", "supplier", "purchase_order", "vat", "duplicate"}

        if str(document.currency.value or "").strip().upper() not in ("EUR", ""):
            triggered.add("currency")
        if document.due_on is not None and document.issued_on is not None:
            triggered.add("payment_terms")
        if not checks.ok:
            triggered.add("vat")
        return triggered

    def subject_terms(self, document: Invoice) -> set[str]:
        """What was bought, for matching `applies_when`.

        Line items and cost centre. The supplier name is excluded on
        purpose: it says who sold, not what was bought, and trading names
        collide with spend categories. "Contoso Cleaning Services BV"
        contributed the token `services`, which matched the "Legal Services"
        ladder and pulled it into a cleaning invoice's evidence.
        """
        terms: set[str] = set()
        if document.cost_centre is not None:
            terms.update(_WORD.findall(str(document.cost_centre.value).lower()))
        for item in document.line_items or []:
            terms.update(_WORD.findall(str(item.description.value).lower()))
        return terms

    def amount(self, document: Invoice) -> Decimal | None:
        """What this document is worth, for approval limits."""
        return document.total_incl_vat.value
