"""Orgs, roles and approval authority (spec section 11).

The scoping itself is tested where it bites, in the API tests. What is
here is the authority rule and the org naming, both of which are pure and
both of which are easy to get subtly wrong in a way nobody notices until a
viewer approves an invoice.
"""

from decimal import Decimal

import pytest

from app.auth.orgs import _default_org_name, may_approve
from app.db.models import Role

# --- who may approve ----------------------------------------------------


@pytest.mark.parametrize("role", [Role.owner, Role.reviewer])
def test_approvers_may_approve_without_a_limit(role):
    assert may_approve(role, None, Decimal("999999"))


def test_a_viewer_may_never_approve():
    """Not even a zero-amount decision, and not even with no limit set."""
    assert not may_approve(Role.viewer, None, Decimal("0"))
    assert not may_approve(Role.viewer, Decimal("1000000"), Decimal("1"))


def test_a_limit_is_inclusive():
    """At the limit is within it. A threshold of 1000 means up to 1000."""
    assert may_approve(Role.reviewer, Decimal("1000"), Decimal("1000"))
    assert not may_approve(Role.reviewer, Decimal("1000"), Decimal("1000.01"))


def test_an_unknown_amount_fails_against_a_limit():
    """"We could not read the total" is not evidence it is under the limit."""
    assert not may_approve(Role.reviewer, Decimal("1000"), None)


def test_an_unknown_amount_is_fine_without_a_limit():
    """Somebody unlimited can take the case a limit cannot be checked for."""
    assert may_approve(Role.owner, None, None)


# --- org naming ---------------------------------------------------------


def test_company_domains_name_the_org():
    assert _default_org_name("finance@northwind.nl") == "Northwind"
    assert _default_org_name("a@acme-corp.co.uk") == "Acme Corp"


@pytest.mark.parametrize(
    "email", ["alex.smith@gmail.com", "alex.smith@outlook.com", "alex.smith@proton.me"]
)
def test_consumer_domains_fall_back_to_the_person(email):
    """Naming an org "Gmail" would be worse than naming it after the user."""
    assert _default_org_name(email) == "Alex Smith"


def test_a_nameless_email_still_produces_something():
    assert _default_org_name("") == "Personal"
