"""The supplier-invoice schema (spec section 7).

This is the vertical, and it is meant to be swapped. The pipeline around
it -- extract, verify spans, check arithmetic, retrieve policy, decide --
knows nothing about invoices. Contract renewals are a sibling module in
this package, not a fork of the pipeline.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.extraction.provenance import ExtractedField

SCHEMA_NAME = "invoice"


class LineItem(BaseModel):
    description: ExtractedField[str]
    quantity: ExtractedField[Decimal]
    unit_price: ExtractedField[Decimal]
    amount: ExtractedField[Decimal] = Field(description="Line total excluding VAT")


class Invoice(BaseModel):
    supplier: ExtractedField[str]
    invoice_number: ExtractedField[str]
    total_incl_vat: ExtractedField[Decimal]
    vat_amount: ExtractedField[Decimal]
    currency: ExtractedField[str] = Field(description="ISO 4217 code, e.g. EUR")
    issued_on: ExtractedField[date]
    due_on: ExtractedField[date] | None = None
    po_number: ExtractedField[str] | None = None
    cost_centre: ExtractedField[str] | None = None
    line_items: list[LineItem] = Field(default_factory=list)

    @property
    def subtotal_excl_vat(self) -> Decimal:
        """Total excluding VAT, from the invoice's own two numbers."""
        return self.total_incl_vat.value - self.vat_amount.value
