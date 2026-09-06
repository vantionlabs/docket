"""The verbatim check on extracted field spans (spec section 7)."""

from decimal import Decimal

import pytest

from app.extraction.provenance import ExtractedField, verify
from app.extraction.schemas.invoice import Invoice, LineItem
from app.grounding.verbatim import contains_verbatim, normalize

DOCUMENT = """# INVOICE

Contoso Cleaning Services BV
Invoice number: CCS-2026-0411
Invoice date: 12 February 2026

| Office cleaning, January 2026 | 1 | 620.00 | 620.00 |

Subtotal excluding VAT: EUR 710.00
VAT 21%: EUR 149.10
Total including VAT: EUR 859.10
"""


def _invoice(**overrides) -> Invoice:
    fields = {
        "supplier": ExtractedField[str](
            value="Contoso Cleaning Services BV", source_span="Contoso Cleaning Services BV"
        ),
        "invoice_number": ExtractedField[str](
            value="CCS-2026-0411", source_span="Invoice number: CCS-2026-0411"
        ),
        "total_incl_vat": ExtractedField[Decimal](
            value=Decimal("859.10"), source_span="Total including VAT: EUR 859.10"
        ),
        "vat_amount": ExtractedField[Decimal](
            value=Decimal("149.10"), source_span="VAT 21%: EUR 149.10"
        ),
        "currency": ExtractedField[str](value="EUR", source_span="EUR 859.10"),
        "issued_on": ExtractedField[str](
            value="2026-02-12", source_span="Invoice date: 12 February 2026"
        ),
    }
    fields.update(overrides)
    return Invoice(**fields)


def test_all_spans_verbatim_verifies():
    assert verify(_invoice(), DOCUMENT).ok


def test_invented_span_is_unverified():
    report = verify(
        _invoice(
            total_incl_vat=ExtractedField[Decimal](
                value=Decimal("8590.10"), source_span="Total including VAT: EUR 8590.10"
            )
        ),
        DOCUMENT,
    )
    assert report.unverified == ["total_incl_vat"]


def test_rewrapped_span_still_verifies():
    """A model that re-wraps a line has not invented anything."""
    report = verify(
        _invoice(
            supplier=ExtractedField[str](
                value="Contoso Cleaning Services BV",
                source_span="contoso   cleaning\nservices BV",
            )
        ),
        DOCUMENT,
    )
    assert report.ok


def test_nested_list_paths_are_reported():
    invoice = _invoice(
        line_items=[
            LineItem(
                description=ExtractedField[str](
                    value="Office cleaning, January 2026",
                    source_span="Office cleaning, January 2026",
                ),
                quantity=ExtractedField[Decimal](value=Decimal(1), source_span="| 1 |"),
                unit_price=ExtractedField[Decimal](value=Decimal("620.00"), source_span="620.00"),
                amount=ExtractedField[Decimal](
                    value=Decimal("620.00"), source_span="a total nobody printed"
                ),
            )
        ]
    )
    assert verify(invoice, DOCUMENT).unverified == ["line_items.0.amount"]


@pytest.mark.parametrize("excerpt", ["", "   ", "\n"])
def test_empty_excerpt_is_never_verbatim(excerpt):
    """A blank span quotes nothing, so it must not verify against anything."""
    assert not contains_verbatim(excerpt, DOCUMENT)


def test_digits_are_not_normalized_away():
    assert not contains_verbatim("EUR 859.11", DOCUMENT)
    assert normalize("  A  B ") == "a b"
