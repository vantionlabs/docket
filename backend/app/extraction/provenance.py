"""Extraction with provenance: every field carries where it came from.

The template turns documents into chunks for chat. This turns them into
typed rows for decisions, and the difference that matters is that a row
used to pay an invoice has to be traceable to the words on the page.

So every extracted field is an `ExtractedField`, carrying the verbatim
`source_span` the model read it from. After extraction, `verify` walks
the model and checks each span really occurs in the parsed document. A
field whose span does not verify is *unverified*: it never feeds an
automatic decision (rail 2, spec section 9). No LLM call, no cost, and it
catches the failure that actually matters, which is a plausible number
the document never contained.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.grounding.verbatim import contains_verbatim


class ExtractedField[T](BaseModel):
    """One extracted value, plus the text it was read from."""

    value: T
    source_span: str = Field(
        description=(
            "The verbatim text from the document this value was read from. "
            "Copy it exactly as it appears; do not paraphrase, reformat or "
            "translate it. If the document does not state this field, omit "
            "the field rather than inventing a span."
        )
    )
    page: int | None = Field(
        default=None, description="1-based page the span appears on, when known"
    )


@dataclass
class VerificationReport:
    """Which field paths failed the verbatim check."""

    unverified: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unverified


def verify(model: BaseModel, document_text: str) -> VerificationReport:
    """Check every `ExtractedField` span in `model` against the document.

    Returns the dotted paths of fields whose span is not verbatim in the
    document, e.g. `["total_incl_vat", "line_items.2.amount"]`.
    """
    report = VerificationReport()
    _walk(model, document_text, path="", report=report)
    return report


def _walk(value: object, document_text: str, path: str, report: VerificationReport) -> None:
    if isinstance(value, ExtractedField):
        if not contains_verbatim(value.source_span, document_text):
            report.unverified.append(path)
        return

    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            child = getattr(value, name)
            _walk(child, document_text, f"{path}.{name}" if path else name, report)
        return

    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _walk(item, document_text, f"{path}.{index}", report)
        return

    if isinstance(value, dict):
        for key, item in value.items():
            _walk(item, document_text, f"{path}.{key}", report)
