"""Verticals: everything that changes when the document type changes.

Spec section 3 claims the pipeline is the product and the vertical is
configuration — "build it so swapping those three is a day, not a fork".
That was aspiration, not fact: `decide.py` carried thirty-three references
to invoices, `coverage.py` fifteen, `rails.py` ten. A second document type
would have meant editing the pipeline.

A `Vertical` bundles the parts that genuinely differ:

  schema          the typed fields, each with a verbatim source span
  dimensions      what kinds of rule a policy can impose on this document
  query           how a retrieval query is built from the extracted fields
  render          how the document is shown to the deciding model
  triggers        which dimensions this document's own data puts in play
  subject_terms   what the document is about, for `applies_when` matching
  checks          the deterministic checks that need no model

Everything else — retrieval, coverage, grounding, the rails, the workflows,
the audit trail — is the pipeline and does not know what an invoice is.

**Dimensions are per-vertical, not global.** A tender has no VAT rate and an
invoice has no delivery window. They stay a closed set within a vertical,
which is what stops an extractor inventing obligations nothing can check;
the database column holds the union.
"""

from app.verticals.base import (
    Vertical,
    all_dimensions,
    get_vertical,
    register_vertical,
    registered_verticals,
)
from app.verticals.invoice import InvoiceVertical
from app.verticals.tender import TenderVertical

register_vertical(InvoiceVertical())
register_vertical(TenderVertical())

__all__ = [
    "Vertical",
    "all_dimensions",
    "get_vertical",
    "register_vertical",
    "registered_verticals",
]
