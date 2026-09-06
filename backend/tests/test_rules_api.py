"""Rules are owner-only, and restrictive by default (spec sections 9, 15).

A rule decides what executes without a human ever seeing it. These tests
pin the two things that keeps safe: who may write one, and what a
half-written one permits.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import rules as rules_router
from app.auth.dependencies import CurrentUser, get_current_user
from app.db.engine import get_db
from app.db.models import Role

ORG = uuid.uuid4()


def _user(role: Role) -> CurrentUser:
    return CurrentUser(id=uuid.uuid4(), email="u@example.com", org_id=ORG, role=role)


def _client(user: CurrentUser):
    db = MagicMock()

    # The real Rule object is built by the router; `created_at` normally
    # comes from a server default, so stand that in on commit or the
    # response model has nothing to serialize.
    added: list = []
    db.add.side_effect = added.append

    def _commit() -> None:
        for row in added:
            if getattr(row, "id", None) is None:
                row.id = uuid.uuid4()
            if getattr(row, "created_at", None) is None:
                row.created_at = datetime.now(UTC)

    db.commit.side_effect = _commit

    app = FastAPI()
    app.include_router(rules_router.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    client.db = db
    client.added = added
    return client


BODY = {
    "name": "cost-centre-owner-limit",
    "conditions": {
        "max_total_incl_vat": "1000",
        "approved_suppliers": ["Contoso Cleaning Services BV"],
        "require_po": True,
    },
    "auto_approve": True,
}


@pytest.mark.parametrize("role", [Role.reviewer, Role.viewer])
def test_only_an_owner_may_create_a_rule(role):
    response = _client(_user(role)).post("/rules", json=BODY)
    assert response.status_code == 403
    assert "Only an owner" in response.json()["detail"]


@pytest.mark.parametrize("role", [Role.reviewer, Role.viewer])
def test_only_an_owner_may_delete_a_rule(role):
    assert _client(_user(role)).delete(f"/rules/{uuid.uuid4()}").status_code == 403


def test_an_owner_may_create_a_rule():
    client = _client(_user(Role.owner))
    assert client.post("/rules", json=BODY).status_code == 201
    created = client.added[0]
    assert created.org_id == ORG
    assert created.conditions["max_total_incl_vat"] == "1000"


def test_auto_approve_is_off_unless_asked_for():
    """The default has to be the safe one: a rule nobody armed approves
    nothing automatically (spec section 4)."""
    client = _client(_user(Role.owner))
    client.post("/rules", json={"name": "unarmed"})
    assert client.added[0].auto_approve is False


def test_a_rule_with_no_ceiling_approves_nothing():
    """Absent conditions are restrictive, never permissive."""
    from app.api.schemas import RuleConditions
    from app.decisions.rails import from_row

    conditions = RuleConditions().model_dump(mode="json")
    assert conditions["max_total_incl_vat"] == "0"

    row = MagicMock(conditions=conditions, active=True, auto_approve=True)
    row.name = "unbounded"
    assert from_row(row).max_total_incl_vat == Decimal("0")


def test_another_orgs_rule_is_not_found():
    client = _client(_user(Role.owner))
    client.db.get.return_value = MagicMock(org_id=uuid.uuid4())
    assert client.delete(f"/rules/{uuid.uuid4()}").status_code == 404
