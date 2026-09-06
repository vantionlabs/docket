"""Arithmetic checks, done in code (spec section 7).

A model asked to add up a column will sometimes add up a column wrong,
and there is no reason to ask it. These checks are deterministic, free,
and they catch both a bad parse and a doctored invoice.

A failure here is not a rejection. It is a reason the case goes to a
human, with the failing sum named so the reviewer knows where to look.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from app.extraction.schemas.invoice import Invoice

# Rounding slack. Invoices round per line, so a cent or two of drift on a
# multi-line total is normal; anything larger is a real disagreement.
TOLERANCE = Decimal("0.02")

# The legal Dutch rates. A rate outside this set means the parse is wrong
# or the invoice is.
LEGAL_VAT_RATES = (Decimal("0"), Decimal("0.09"), Decimal("0.21"))
VAT_RATE_TOLERANCE = Decimal("0.005")


@dataclass
class ArithmeticReport:
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def check_invoice(invoice: Invoice) -> ArithmeticReport:
    report = ArithmeticReport()
    subtotal = invoice.subtotal_excl_vat

    if invoice.line_items:
        lines_total = sum((item.amount.value for item in invoice.line_items), Decimal(0))
        if abs(lines_total - subtotal) > TOLERANCE:
            report.failures.append(
                f"line items sum to {lines_total}, but total minus VAT is {subtotal}"
            )

        for index, item in enumerate(invoice.line_items):
            expected = item.quantity.value * item.unit_price.value
            if abs(expected - item.amount.value) > TOLERANCE:
                report.failures.append(
                    f"line {index + 1}: {item.quantity.value} x {item.unit_price.value} "
                    f"is {expected}, but the line reads {item.amount.value}"
                )

    if subtotal < 0:
        report.failures.append(
            f"VAT {invoice.vat_amount.value} exceeds total {invoice.total_incl_vat.value}"
        )
    elif subtotal > 0:
        rate = invoice.vat_amount.value / subtotal
        if not any(abs(rate - legal) <= VAT_RATE_TOLERANCE for legal in LEGAL_VAT_RATES):
            report.failures.append(
                f"VAT rate works out to {rate:.4f}, which is not a legal Dutch rate "
                f"({', '.join(str(r) for r in LEGAL_VAT_RATES)})"
            )
    elif invoice.vat_amount.value != 0:
        report.failures.append(f"VAT is {invoice.vat_amount.value} on a subtotal of zero")

    return report
