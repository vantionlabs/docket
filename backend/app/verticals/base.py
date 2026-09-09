"""The Vertical protocol and its registry."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel

from app.logging import get_logger

log = get_logger(__name__)


@dataclass
class DeterministicChecks:
    """What can be checked without a model, and what it found.

    Every vertical has some. Invoices have arithmetic; a tender has dates
    that must fall in order and a deposit that cannot exceed the contract
    value. Doing these in code rather than asking a model is the same
    argument in both cases: a model asked to add up a column will sometimes
    add up a column wrong, and there is no reason to ask.
    """

    ok: bool = True
    failures: list[str] = field(default_factory=list)


def warnings_block(checks: DeterministicChecks, unverified: list[str]) -> list[str]:
    """The warning lines every vertical shows the deciding model.

    Shared because they are about the pipeline's own confidence, not about
    the document: "this field could not be verified" and "the checks did not
    pass" mean the same thing whatever the document is.
    """
    lines: list[str] = []
    if unverified:
        lines.append(
            "  WARNING, these fields could not be verified against the document "
            f"and may be wrong: {', '.join(unverified)}"
        )
    if checks.failures:
        lines.append("  WARNING, the deterministic checks did not pass:")
        lines.extend(f"    - {failure}" for failure in checks.failures)
    return lines


class Vertical(Protocol):
    """One document type, and everything that changes with it."""

    name: str
    schema: type[BaseModel]
    dimensions: frozenset[str]
    """Which rule kinds a policy can impose on this document. Closed, so an
    extractor cannot invent one nothing evaluates."""

    def query(self, document: BaseModel) -> str:
        """The policy question this document asks, in the policy's words."""
        ...

    def render(
        self, document: BaseModel, checks: DeterministicChecks, unverified: list[str]
    ) -> str:
        """How the document is shown to the deciding model."""
        ...

    def triggers(self, document: BaseModel, checks: DeterministicChecks) -> set[str]:
        """Which dimensions this document's own data puts in play."""
        ...

    def subject_terms(self, document: BaseModel) -> set[str]:
        """What this document is about, for matching `applies_when`."""
        ...

    def check(self, document: BaseModel) -> DeterministicChecks:
        """Run the checks that need no model."""
        ...

    def amount(self, document: BaseModel) -> Decimal | None:
        """What this document is worth, where it says.

        The one number every vertical has to be able to produce, because
        every question asked of decision history — what a threshold change
        is worth, what a clause governs in euros — is asked in money. None
        when the document does not state one.
        """
        ...


_VERTICALS: dict[str, Vertical] = {}


def register_vertical(vertical: Vertical) -> Vertical:
    if vertical.name in _VERTICALS:
        raise ValueError(f"vertical already registered under {vertical.name!r}")
    _VERTICALS[vertical.name] = vertical
    return vertical


def get_vertical(name: str) -> Vertical:
    """The vertical by name. Unknown names raise rather than defaulting.

    Falling back to invoices would decide a tender against procurement
    thresholds and look like it worked.
    """
    try:
        return _VERTICALS[name]
    except KeyError as exc:
        raise KeyError(
            f"No vertical registered for {name!r}. Known: {sorted(_VERTICALS)}"
        ) from exc


def registered_verticals() -> list[str]:
    return sorted(_VERTICALS)


def all_dimensions() -> frozenset[str]:
    """Every dimension any vertical uses. The database column's domain."""
    return frozenset().union(*(v.dimensions for v in _VERTICALS.values()))
