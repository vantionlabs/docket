"""Arithmetic checks run in code, never by the model (spec section 7)."""

from decimal import Decimal

from app.extraction.arithmetic import check_invoice
from app.extraction.provenance import ExtractedField
from app.extraction.schemas.invoice import Invoice, LineItem


def _field(value):
    return ExtractedField(value=value, source_span=str(value))


def _line(quantity, unit_price, amount):
    return LineItem(
        description=_field("thing"),
        quantity=_field(Decimal(quantity)),
        unit_price=_field(Decimal(unit_price)),
        amount=_field(Decimal(amount)),
    )


def _invoice(total, vat, lines=()):
    return Invoice(
        supplier=_field("Contoso Cleaning Services BV"),
        invoice_number=_field("CCS-1"),
        total_incl_vat=_field(Decimal(total)),
        vat_amount=_field(Decimal(vat)),
        currency=_field("EUR"),
        issued_on=_field("2026-02-12"),
        line_items=list(lines),
    )


def test_consistent_invoice_passes():
    invoice = _invoice(
        "859.10", "149.10", [_line("1", "620.00", "620.00"), _line("4", "22.50", "90.00")]
    )
    assert check_invoice(invoice).ok


def test_line_items_not_summing_to_subtotal_fails():
    invoice = _invoice(
        "2136.78", "318.78", [_line("3", "410.00", "1230.00"), _line("6", "48.00", "288.00")]
    )
    failures = check_invoice(invoice).failures
    assert any("line items sum to" in f for f in failures)


def test_line_quantity_times_price_is_checked():
    invoice = _invoice("1210.00", "210.00", [_line("2", "400.00", "1000.00")])
    assert any("line 1" in f for f in check_invoice(invoice).failures)


def test_illegal_vat_rate_fails():
    """13 percent is not a Dutch rate, so this is a bad parse or a bad invoice."""
    invoice = _invoice("1130.00", "130.00")
    assert any("not a legal Dutch rate" in f for f in check_invoice(invoice).failures)


def test_zero_rated_invoice_passes():
    assert check_invoice(_invoice("8400.00", "0")).ok


def test_vat_exceeding_total_fails():
    assert any("exceeds total" in f for f in check_invoice(_invoice("100.00", "150.00")).failures)


def test_penny_rounding_is_tolerated():
    invoice = _invoice(
        "859.11", "149.10", [_line("1", "620.00", "620.00"), _line("4", "22.50", "90.00")]
    )
    assert check_invoice(invoice).ok
