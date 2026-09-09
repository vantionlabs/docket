"""The approval endpoints, and the collection filter behind them.

Offline: the database is a fake and auth is overridden. What is under test
is the contract, which is where the interesting rules live. Approving must
be safe to repeat, a reviewer must not be able to grant automatic
execution, and a decision must never retrieve its policy from the pile of
documents it belongs to.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import decisions as decisions_router
from app.auth.dependencies import CurrentUser, get_current_user
from app.db.engine import get_db
from app.db.models import Collection, DecisionStatus, Role
from app.decisions.models import Outcome

ORG = uuid.uuid4()
USER = CurrentUser(
    id=uuid.uuid4(),
    email="reviewer@example.com",
    org_id=ORG,
    role=Role.owner,
    approval_limit=None,
)


def _decision(status=DecisionStatus.pending_review, **overrides):
    """A decision row shaped like the real one.

    A bare MagicMock was enough while the tests only mutated it, and stopped
    being enough the moment an endpoint serialized it: every unset attribute
    became a MagicMock that failed validation. Filling the fields in makes
    the failure "this endpoint is wrong" rather than "the mock is thin".
    """
    row = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=USER.id,
        org_id=ORG,
        document_id=uuid.uuid4(),
        extraction_id=None,
        outcome=str(Outcome.route_for_approval),
        effective_outcome=str(Outcome.route_for_approval),
        rationale="Under the limit [1].",
        unmet_conditions=[],
        rail_notes=[],
        rule_id=None,
        grounding_passed=True,
        grounding_failure=None,
        status=status,
        assigned_to=None,
        reviewed_by=None,
        reviewed_at=None,
        override_outcome=None,
        override_note=None,
        created_at=datetime.now(UTC),
        citations=[],
        filename="",
        supplier=None,
        amount=None,
        currency=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


@pytest.fixture
def client(monkeypatch):
    return _client(monkeypatch, USER)


def _client(monkeypatch, user: CurrentUser):
    db = MagicMock()
    app = FastAPI()
    app.include_router(decisions_router.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db

    emitted: list[tuple] = []

    def _emit(session, decision, action):
        emitted.append((decision.id, action))
        return MagicMock(id=uuid.uuid4())

    monkeypatch.setattr(decisions_router, "emit_execute", _emit)

    test_client = TestClient(app)
    test_client.db = db
    test_client.emitted = emitted
    return test_client


# --- approve ------------------------------------------------------------


def test_approve_emits_the_execute_event(client):
    decision = _decision()
    client.db.get.return_value = decision

    response = client.post(f"/decisions/{decision.id}/approve", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert client.emitted == [(decision.id, "approve_for_payment")]
    assert decision.reviewed_by == USER.id


def test_approving_twice_does_not_execute_twice(client):
    """A double-clicked approve returns the state and emits nothing new."""
    decision = _decision(status=DecisionStatus.approved)
    client.db.get.return_value = decision

    response = client.post(f"/decisions/{decision.id}/approve", json={})
    assert response.status_code == 200
    assert client.emitted == []


def test_approving_an_executed_decision_is_a_no_op(client):
    decision = _decision(status=DecisionStatus.executed)
    client.db.get.return_value = decision
    assert client.post(f"/decisions/{decision.id}/approve", json={}).status_code == 200
    assert client.emitted == []


def test_approving_a_rejected_decision_is_a_conflict(client):
    decision = _decision(status=DecisionStatus.rejected)
    client.db.get.return_value = decision
    response = client.post(f"/decisions/{decision.id}/approve", json={})
    assert response.status_code == 409


def test_override_is_recorded_beside_the_original(client):
    """The disagreement is the measurement. The original outcome stays."""
    decision = _decision(outcome=str(Outcome.reject))
    client.db.get.return_value = decision

    response = client.post(
        f"/decisions/{decision.id}/approve",
        json={"override_outcome": "route_for_approval", "note": "Contract supersedes."},
    )
    assert response.status_code == 200
    assert decision.outcome == str(Outcome.reject)
    assert decision.override_outcome == "route_for_approval"
    assert decision.override_note == "Contract supersedes."


def test_a_reviewer_cannot_grant_automatic_execution(client):
    """Rail 3: a rule authorises auto-approve, not a person approving a case."""
    decision = _decision()
    client.db.get.return_value = decision

    response = client.post(
        f"/decisions/{decision.id}/approve", json={"override_outcome": "auto_approve"}
    )
    assert response.status_code == 422
    assert "not something a reviewer may choose" in response.json()["detail"]
    assert client.emitted == []


def test_unknown_override_outcome_is_rejected(client):
    decision = _decision()
    client.db.get.return_value = decision
    response = client.post(
        f"/decisions/{decision.id}/approve", json={"override_outcome": "pay_it_anyway"}
    )
    assert response.status_code == 422


def test_another_orgs_decision_is_not_found(client):
    """404, not 403: the API never confirms a foreign row exists.

    Scoped by org, not user: a reviewer must be able to open a case
    somebody else's intake created, and must not be able to open another
    company's (spec section 11)."""
    client.db.get.return_value = _decision(org_id=uuid.uuid4())
    response = client.post(f"/decisions/{uuid.uuid4()}/approve", json={})
    assert response.status_code == 404


def test_a_colleague_in_the_same_org_can_approve(client):
    """The queue is shared. That is the point of it."""
    decision = _decision(user_id=uuid.uuid4())  # somebody else's intake
    client.db.get.return_value = decision
    assert client.post(f"/decisions/{decision.id}/approve", json={}).status_code == 200


# --- approval authority: role plus threshold (spec section 11) ----------


def _member(role, limit=None):
    return CurrentUser(
        id=uuid.uuid4(), email="m@example.com", org_id=ORG, role=role, approval_limit=limit
    )


def test_a_viewer_may_not_approve(monkeypatch):
    client = _client(monkeypatch, _member(Role.viewer))
    decision = _decision()
    client.db.get.return_value = decision
    response = client.post(f"/decisions/{decision.id}/approve", json={})
    assert response.status_code == 403
    assert "may not approve" in response.json()["detail"]
    assert client.emitted == []


def test_a_viewer_may_not_reject_either(monkeypatch):
    """Closing a case is an act on it too."""
    client = _client(monkeypatch, _member(Role.viewer))
    decision = _decision()
    client.db.get.return_value = decision
    assert client.post(f"/decisions/{decision.id}/reject", json={}).status_code == 403


def test_a_reviewer_may_not_approve_above_their_limit(monkeypatch):
    client = _client(monkeypatch, _member(Role.reviewer, Decimal("1000")))
    decision = _decision(extraction_id=uuid.uuid4())
    extraction = MagicMock(fields={"total_incl_vat": {"value": "12196.80"}})
    client.db.get.side_effect = lambda model, _id: (
        decision if model.__name__ == "Decision" else extraction
    )
    response = client.post(f"/decisions/{decision.id}/approve", json={})
    assert response.status_code == 403
    assert "above your approval limit" in response.json()["detail"]
    assert client.emitted == []


def test_a_reviewer_may_approve_within_their_limit(monkeypatch):
    client = _client(monkeypatch, _member(Role.reviewer, Decimal("1000")))
    decision = _decision(extraction_id=uuid.uuid4())
    extraction = MagicMock(fields={"total_incl_vat": {"value": "859.10"}})
    client.db.get.side_effect = lambda model, _id: (
        decision if model.__name__ == "Decision" else extraction
    )
    assert client.post(f"/decisions/{decision.id}/approve", json={}).status_code == 200
    assert client.emitted


def test_an_unreadable_total_cannot_be_approved_under_a_limit(monkeypatch):
    """A ceiling exists for a reason, and "we could not read the total" is
    not evidence that the total is under it."""
    client = _client(monkeypatch, _member(Role.reviewer, Decimal("1000")))
    decision = _decision(extraction_id=uuid.uuid4())
    extraction = MagicMock(fields={"total_incl_vat": {"value": None}})
    client.db.get.side_effect = lambda model, _id: (
        decision if model.__name__ == "Decision" else extraction
    )
    response = client.post(f"/decisions/{decision.id}/approve", json={})
    assert response.status_code == 403
    assert "no readable total" in response.json()["detail"]


def test_an_unlimited_member_can_take_an_unreadable_total(monkeypatch):
    client = _client(monkeypatch, _member(Role.owner, None))
    decision = _decision(extraction_id=uuid.uuid4())
    extraction = MagicMock(fields={})
    client.db.get.side_effect = lambda model, _id: (
        decision if model.__name__ == "Decision" else extraction
    )
    assert client.post(f"/decisions/{decision.id}/approve", json={}).status_code == 200


# --- reject -------------------------------------------------------------


def test_reject_executes_nothing(client):
    decision = _decision()
    client.db.get.return_value = decision

    response = client.post(f"/decisions/{decision.id}/reject", json={"note": "Duplicate."})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert client.emitted == []
    assert decision.override_note == "Duplicate."


def test_rejecting_twice_is_a_no_op(client):
    decision = _decision(status=DecisionStatus.rejected)
    client.db.get.return_value = decision
    assert client.post(f"/decisions/{decision.id}/reject", json={}).status_code == 200


# --- the detail screen's field flattening -------------------------------


def test_fields_are_flattened_with_their_spans_and_verification():
    flatten = decisions_router._flatten_fields
    rows = flatten(
        {
            "supplier": {"value": "Contoso", "source_span": "Contoso", "page": None},
            "line_items": [
                {
                    "amount": {"value": "620.00", "source_span": "620.00", "page": None},
                }
            ],
        },
        unverified={"line_items.0.amount"},
    )
    by_name = {row.name: row for row in rows}
    assert by_name["supplier"].verified is True
    assert by_name["supplier"].source_span == "Contoso"
    assert by_name["line_items.0.amount"].verified is False


def test_flattened_paths_match_the_verifier_paths():
    """The detail screen highlights a field by path, so these two have to
    agree. If they drift, the wrong field lights up as unverified."""
    from decimal import Decimal

    from app.extraction.provenance import ExtractedField, verify
    from app.extraction.schemas.invoice import Invoice, LineItem

    def _f(value, span):
        return ExtractedField(value=value, source_span=span)

    invoice = Invoice(
        supplier=_f("Contoso", "Contoso"),
        invoice_number=_f("CCS-1", "CCS-1"),
        total_incl_vat=_f(Decimal("859.10"), "859.10"),
        vat_amount=_f(Decimal("149.10"), "149.10"),
        currency=_f("EUR", "EUR"),
        issued_on=_f("2026-02-12", "12 February 2026"),
        line_items=[
            LineItem(
                description=_f("cleaning", "cleaning"),
                quantity=_f(Decimal(1), "1"),
                unit_price=_f(Decimal("620.00"), "620.00"),
                amount=_f(Decimal("620.00"), "nowhere in the document"),
            )
        ],
    )
    document = "Contoso CCS-1 859.10 149.10 EUR 12 February 2026 cleaning 1 620.00"
    unverified = verify(invoice, document).unverified
    assert unverified == ["line_items.0.amount"]

    import json

    names = {
        row.name
        for row in decisions_router._flatten_fields(
            json.loads(invoice.model_dump_json()), set(unverified)
        )
    }
    assert set(unverified) <= names


# --- the collection filter (spec section 8) -----------------------------


def test_policy_retrieval_is_confined_to_the_policy_collection(monkeypatch):
    """A decision must never be able to cite the invoice it is deciding."""
    from app.decisions.policy import RetrievedPolicy

    seen: dict = {}

    def _fake_search(user_id, query, collection=None, top_k=None):
        seen["collection"] = collection
        seen["top_k"] = top_k
        return []

    monkeypatch.setattr("app.retrieval.hybrid.hybrid_search", _fake_search)
    RetrievedPolicy(uuid.uuid4()).retrieve("spend threshold", top_k=5)
    assert seen["collection"] is Collection.policy
    assert seen["top_k"] == 5


def test_collection_filter_is_absent_only_when_no_collection_is_asked_for():
    from app.retrieval.hybrid import _collection_clause, _collection_params

    assert _collection_clause(None) == ""
    assert _collection_params(None) == {}
    assert "c.collection = :collection" in _collection_clause(Collection.policy)
    assert _collection_params(Collection.policy) == {"collection": "policy"}


def test_retrieved_clause_keeps_its_chunk_provenance(monkeypatch):
    """A citation has to be storable against the row it quoted."""
    from app.decisions.policy import RetrievedPolicy
    from app.retrieval.hybrid import RetrievedChunk

    chunk = RetrievedChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=2,
        content="## 3. Spend thresholds\n\nUp to EUR 1,000: the cost centre owner may approve.",
        filename="procurement-policy.md",
    )
    monkeypatch.setattr(
        "app.retrieval.hybrid.hybrid_search", lambda *a, **k: [chunk]
    )
    clause = RetrievedPolicy(uuid.uuid4()).retrieve("threshold")[0]
    assert clause.chunk_id == chunk.id
    assert clause.document_id == chunk.document_id
    assert clause.ref == "procurement-policy.md, 3. Spend thresholds"


def test_clause_ref_falls_back_to_a_position_when_there_is_no_heading():
    from app.decisions.policy import _clause_ref

    assert _clause_ref("policy.md", "no heading here", 4) == "policy.md, part 5"


def test_decided_at_is_not_the_review_time():
    """Sanity on the audit trail: these are different moments."""
    decided = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)
    reviewed = datetime(2026, 9, 8, 9, 30, tzinfo=UTC)
    assert decided < reviewed


# --- the detail screen's payload ----------------------------------------


def _detail_client(monkeypatch, decision, extraction, filename="invoice.md"):
    """A client whose db returns a decision, its extraction and its document.

    Worth the setup: the detail endpoint assembles four sources into one
    payload, and it broke once by passing `filename` twice after the field
    moved onto the shared summary. That was a 500 the UI rendered as
    "Not found", which is the worst kind of bug to debug from the outside.
    """
    from app.db.models import Decision as DecisionModel
    from app.db.models import Extraction as ExtractionModel

    client = _client(monkeypatch, USER)

    def _get(model, _id):
        if model is DecisionModel:
            return decision
        if model is ExtractionModel:
            return extraction
        return MagicMock(filename=filename)

    client.db.get.side_effect = _get
    # `_summarize` issues two selects: documents, then extractions. Rows come
    # back as objects with named columns, not tuples.
    client.db.execute.side_effect = [
        [SimpleNamespace(id=decision.document_id, filename=filename)],
        [SimpleNamespace(id=extraction.id, fields=extraction.fields)],
    ]
    return client


def test_detail_assembles_without_duplicating_a_field(monkeypatch):
    decision = _decision(extraction_id=uuid.uuid4())
    extraction = MagicMock(
        id=decision.extraction_id,
        schema_name="invoice",
        document_text="Fabrikam Office Supplies BV\nTotal including VAT: EUR 12196.80",
        unverified_fields=[],
        checks_ok=True,
        check_failures=[],
        fields={
            "supplier": {"value": "Fabrikam Office Supplies BV", "source_span": "Fabrikam"},
            "total_incl_vat": {"value": "12196.80", "source_span": "12196.80"},
        },
    )
    client = _detail_client(monkeypatch, decision, extraction)

    response = client.get(f"/decisions/{decision.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["document_text"].startswith("Fabrikam")
    assert body["supplier"] == "Fabrikam Office Supplies BV"
    assert body["amount"] == "12196.80"


def test_detail_orders_fields_by_the_schema_not_by_storage(monkeypatch):
    """Postgres JSONB does not preserve key order, so without this the
    reviewer meets `due_on` before `supplier`."""
    decision = _decision(extraction_id=uuid.uuid4())
    extraction = MagicMock(
        id=decision.extraction_id,
        schema_name="invoice",
        document_text="",
        unverified_fields=[],
        checks_ok=True,
        check_failures=[],
        # Deliberately scrambled, the way JSONB hands it back.
        fields={
            "due_on": {"value": "2026-04-02", "source_span": "2 April 2026"},
            "line_items": [
                {"amount": {"value": "5760.0", "source_span": "5760.00"}},
            ],
            "total_incl_vat": {"value": "12196.80", "source_span": "12196.80"},
            "supplier": {"value": "Fabrikam", "source_span": "Fabrikam"},
        },
    )
    client = _detail_client(monkeypatch, decision, extraction)

    names = [row["name"] for row in client.get(f"/decisions/{decision.id}").json()["fields"]]
    assert names.index("supplier") < names.index("total_incl_vat")
    assert names.index("total_incl_vat") < names.index("due_on")
    # Line items are components, and they come after the headline fields.
    assert names.index("due_on") < names.index("line_items.0.amount")


def test_unknown_schema_still_renders(monkeypatch):
    """A stored extraction from a schema this build no longer has must not
    take the screen down with it."""
    decision = _decision(extraction_id=uuid.uuid4())
    extraction = MagicMock(
        id=decision.extraction_id,
        schema_name="contract_renewal_v0",
        document_text="",
        unverified_fields=[],
        checks_ok=True,
        check_failures=[],
        fields={"counterparty": {"value": "Acme", "source_span": "Acme"}},
    )
    client = _detail_client(monkeypatch, decision, extraction)
    response = client.get(f"/decisions/{decision.id}")
    assert response.status_code == 200
    assert response.json()["fields"][0]["name"] == "counterparty"
