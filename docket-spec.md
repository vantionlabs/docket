# Docket — document-to-decision pipeline (build spec)

> **What it is.** Documents arrive. The pipeline reads them, extracts the fields
> that matter, checks them against the client's own written policy, and produces a
> decision with the clause that justified it attached. Clean cases execute on
> their own. Everything else lands in a queue where a person approves it in
> seconds.
>
> **The refusal is the product.** Anything can draft an answer. What makes this
> sellable is that it knows when it is not allowed to decide, says why, and
> escalates — and that every automatic decision carries a citation somebody can
> audit a year later.

Status: spec. Written 6 Sep 2026. Nothing built yet.

---

## 1. Where it lives

**A new standalone repo, copied out of `templates/ai-project`.** Not the hub, not
a branch of the template.

```bash
cp -r ~/stacklane/projects/stacklane-new/templates/ai-project/. \
      ~/stacklane/ai-projects/docket/     # this spec already lives there
cd ~/stacklane/ai-projects/docket && rm -rf backend/.venv backend/.pytest_cache \
      backend/.ruff_cache && git init
```

The template already says it: standalone, own lockfiles, copied out per client.
This is the first copy that goes further than the template does, and some of what
it grows belongs back in the template afterwards — deliberately, §14, not by
accident.

Keep the template's `AGENTS.md` and extend it. It carries the conventions the
engine depends on.

## 2. Why this one

Two audiences, one build: a portfolio piece and the reference implementation an
agency can resell.

The template already ships the parts most people would call the advanced project
— hybrid retrieval with RRF, a fail-closed grounding validator with an LLM judge,
an event engine with retries, dead-lettering, idempotency and crash recovery, an
eval harness, per-call cost logging. So the interesting work is not another
retrieval trick. It is the four things the template deliberately left out:

| Missing | Where it shows |
|---|---|
| The agent cannot act | Every tool in `app/agent/tools.py` reads. Nothing writes |
| No structured extraction | Documents become chunks for chat, never typed rows |
| No human in the loop | A workflow runs to completion or dead-letters. It cannot stop and wait for a person |
| No orgs | `docs/architecture.md` lists multi-tenancy as an explicit non-goal |

Fill those four and you have a category of product rather than a demo.

**What makes it demo well.** The standard AI demo shows the happy path. This one
shows an agent declining to decide, naming the policy it could not satisfy, and
handing the case to a named human. In a sales conversation that lands harder than
a hundred correct answers.

**What makes it sell.** It maps onto the €7k build-plus-automation slot almost
literally: one intake process, one policy corpus, one system of record adapter.
And it is the same pipeline for every client, so the second one is configuration
plus an adapter rather than a rebuild.

## 3. The worked example, and the honest framing

**Worked example: supplier invoices checked against a procurement policy.** Every
company has them, the policy already exists in writing, and the actions are real:
approve for payment, route to a cost-centre owner, reject with a reason.

**The pipeline is the product. The vertical is configuration.** Contract renewals,
insurance claims, onboarding paperwork, expense reports, grant applications and
tender compliance are the same four steps with a different schema, a different
policy corpus and a different adapter. Build it so swapping those three is a day,
not a fork.

Invoices are a crowded market. That is a feature here: the buyer needs no
education about the value, so the whole conversation is about the differentiator,
which is the audit trail.

## 4. Scope

**In scope**

- Intake by signed webhook, scheduled pull, or upload
- Extraction to a typed schema, with a source span behind every field
- Retrieval against the client's own policy corpus, kept separate from the
  documents being decided
- A decision, with citations to the specific clauses that justified it
- A hard rail: no ungrounded decision ever executes automatically
- A review queue where a human approves, edits or rejects, in seconds
- Execution of the approved action against a system of record, idempotently
- A complete audit trail: what arrived, what was extracted, what was cited, who
  approved, what fired
- Orgs, members and roles, because no client buys this single-tenant

**Out of scope, deliberately**

| Excluded | Why |
|---|---|
| Auto-execute on day one | v1 ships with every decision queued. Auto-execute turns on per rule, per client, after the eval set says it is safe. §13 |
| Fine-tuning | The corpus is the client's policy documents. Retrieval and a good schema beat a tuned model here, and a tuned model cannot cite |
| OCR beyond what docling gives | Scanned-fax invoices are a real problem and a separate project. v1 takes digital PDFs and fails loudly on the rest |
| Direct ERP/accounting integrations, plural | One adapter, chosen per client. A plugin surface, not a marketplace |
| Queue-backed chat | Chat stays synchronous SSE. That decision in the template was right |
| Agent-authored policy | The model reads policy. It never writes or amends it |
| Free-text decisions | Decisions come from a closed enum. A model that can invent an outcome can invent an outcome nobody has a process for |

## 5. Architecture

```
INTAKE                  DECIDE (workflow)              HUMAN            EXECUTE
webhook /               MarkProcessing                 review queue     (workflow)
 schedule /             FetchFromR2                    approve  ─┐      CheckIdempotency
 upload                 ParseDocument                  edit      │      CallAdapter
   │                    ExtractFields   ──┐            reject   ─┤      RecordExecution
   │                    RetrievePolicy    │ provenance           │      NotifySubmitter
   ▼                    Decide            │ checks               │            ▲
 events row ──────────> ValidateGrounding ┘                      │            │
 (document.decide)      RouteOutcome (RouterNode)                │            │
                          ├── auto ──> emit decision.execute ────┼────────────┘
                          └── review ─> decisions.pending ───────┘
                                                          (approval emits the same event)
```

Two workflows, joined by an event. That split is the whole trick, §6.

Both halves write to `decisions`. Everything an auditor needs is on that row or
the `events` rows either side of it.

## 6. The pause: how a workflow waits for a human

**The problem.** `Workflow.run` walks nodes to completion or raises. There is no
suspend. An approval can take three days, so the naive designs are a worker
thread blocked for three days, or a state machine bolted onto the side.

**The design: do not suspend. Split at the human boundary and let the event row be
the checkpoint.**

The decide workflow ends by writing a `decisions` row with status
`pending_review` and returning. The task finishes cleanly, in seconds. The human
approves via `POST /decisions/{id}/approve`, which emits a `decision.execute`
event through `app.core.intake.create_event`, and the execute workflow runs the
side effects. Auto-approved decisions emit exactly the same event from the router
node, so there is one execution path and the approval is just a different way to
reach it.

**Why this beats a durable-suspend primitive.** The event row already is the
durable checkpoint: `status`, `attempts`, `result`, `error`, with retries,
dead-lettering, idempotency and stale-sweep recovery around it. Splitting gets
all of that for free, keeps every workflow short-lived, survives deploys with no
special handling, and means a pending decision is a database row anyone can
query rather than a suspended coroutine somebody has to trust.

This is also the honest answer to the LangGraph question. Its checkpoint-and-
interrupt model is the one genuinely valuable idea over there, and cutting the
workflow at the human boundary gives the same property without importing a
second execution engine to sit beside the one that already works.

**What we give up.** A decision that needs two sequential approvals is two rows
and two events rather than one paused run. Fine at this size. If approval chains
get deep, that is the moment to consider a real suspend, not before.

## 7. Extraction with provenance

Extraction is a PydanticAI call with a typed output model, using the same
`app.llm.providers.chat_model()` seam so the provider stays a config change.

**Every field carries where it came from.**

```python
class ExtractedField[T](BaseModel):
    value: T
    source_span: str   # verbatim text from the document
    page: int | None

class Invoice(BaseModel):
    supplier: ExtractedField[str]
    invoice_number: ExtractedField[str]
    total_incl_vat: ExtractedField[Decimal]
    vat_amount: ExtractedField[Decimal]
    currency: ExtractedField[str]
    issued_on: ExtractedField[date]
    due_on: ExtractedField[date | None]
    po_number: ExtractedField[str | None]
    line_items: list[LineItem]
```

Then a structural check, the same discipline the grounding validator already
applies to answers: **is `source_span` verbatim in the parsed document?** If not,
that field is unverified. Unverified fields force review; they never feed an
automatic decision. No LLM call, no cost, catches the failure that matters.

Arithmetic is checked in code, not by the model. Line items sum to subtotal,
subtotal plus VAT equals total, VAT rate is one of the legal Dutch rates. A model
asked to add up a column will sometimes add up a column wrong, and there is no
reason to ask it.

## 8. The policy check

The decision is grounded in a **separate corpus**: the client's procurement
policy, spend thresholds, delegation-of-authority matrix, approved supplier list,
signed contracts. Not the invoice.

**This needs a change to retrieval.** `hybrid_search(user_id, query)` filters on
`user_id` only. Add a `collection` to `source_documents` and `document_chunks`
(`policy` | `transactional`) and filter on it, so a policy question can never
retrieve an invoice and an invoice can never quietly become policy. Small change,
and it is the first thing that goes back into the template.

Retrieval otherwise stays as built: pgvector HNSW plus Postgres FTS, fused with
RRF, optional rerank, neighbour expansion. It works. The queries are generated
from the extracted fields rather than typed by a user — supplier name, amount
band, cost centre, category — which makes them more consistent than chat queries
and is part of why this is easier to get right than open chat.

## 9. Decision and the hard rails

Output is a closed enum plus mandatory citations:

```python
class Outcome(StrEnum):
    auto_approve = "auto_approve"
    route_for_approval = "route_for_approval"
    reject = "reject"
    needs_human = "needs_human"

class Decision(BaseModel):
    outcome: Outcome
    rationale: str                      # with [n] markers
    citations: list[PolicyCitation]     # clause + verbatim excerpt
    assignee_hint: str | None           # cost centre or role, never a person
    unmet_conditions: list[str]
```

Then the existing validator runs, repointed from answer-chunks to policy-clauses:
structural check first — do the markers match the citations, is every cited
clause in the turn registry, is every excerpt verbatim — then the LLM judge on
whether each excerpt actually supports the claim it is attached to.

**Three hard rails. These are the spec, not an opening position.**

1. **A decision that fails grounding never executes.** It becomes `needs_human`
   with the failure attached. Fail-closed, same as the template's chat.
2. **Any unverified extracted field forces review**, whatever the outcome says.
3. **Auto-approve is gated by an explicit rule**, not by model confidence. Amount
   under the threshold, supplier on the approved list, PO matched, no unmet
   conditions, grounding passed. The model proposes; the rule decides whether a
   human sees it. A model's own confidence score is not an authorisation.

The reviewer's edit is training data for nobody and evidence for everybody: store
the original decision alongside the override so the disagreement rate is
measurable per rule. That number is what tells a client when to widen a
threshold.

## 10. Execution and idempotency

Events retry. Side effects that call a payment or accounting system must therefore
be idempotent or someone gets paid twice.

- Write an `executions` row with a unique idempotency key **before** the outbound
  call, derived from `decision_id` plus action. A retry that finds a completed row
  returns it and does nothing.
- Adapters are a Protocol with three implementations to start: `DryRunAdapter`
  (logs and returns a fake reference — the default, and what demos run on),
  `EmailAdapter` (sends the approved instruction via the Resend client the
  template already wires up), and one real one per client.
- Every adapter call, request and response, lands on the `executions` row.

`DryRunAdapter` as the default is what makes this safe to show to a prospect with
their own documents in it.

## 11. Multi-tenancy

The template's explicit non-goal, and the single biggest lift here. Nobody buys
an approval queue that cannot tell two companies apart.

- `organizations`, `memberships(org_id, user_id, role)`; roles `owner`,
  `reviewer`, `viewer`.
- `org_id` on every domain table, and on `events` so a workflow knows its tenant.
- Scope at the dependency seam, not at each call site: extend the
  `get_current_user` contract to carry the active org, and make the retrieval and
  query helpers take it. Ownership stays app-layer, matching the template's
  existing decision, but every filter that reads `user_id` today gets read again
  with this in mind.
- Approval authority is a role plus a threshold, held on the membership.

This is also the most reusable thing built here, §14.

## 12. Domain model

New Alembic migrations. The template's `source_documents` and `document_chunks`
gain `collection` and `org_id`; everything else is new.

```
organizations(id, name, created_at)
memberships(id, org_id, user_id, role, approval_limit, created_at)

intakes(id, org_id, source, external_ref UNIQUE, document_id,
        received_at, raw jsonb)

extractions(id, org_id, document_id, schema_name, fields jsonb,
            unverified_fields text[], arithmetic_ok, model, created_at)

decisions(id, org_id, document_id, extraction_id,
          outcome, rationale, unmet_conditions text[],
          rule_id, grounding_passed, status,
          -- status: pending_review | approved | rejected | executed | failed
          assigned_to, decided_at, reviewed_by, reviewed_at,
          override_outcome, override_note, created_at)

decision_citations(id, decision_id, chunk_id, document_id,
                   citation_index, clause_ref, excerpt)

rules(id, org_id, name, schema_name, conditions jsonb, auto_approve bool,
      active, created_at)

executions(id, org_id, decision_id, adapter, idempotency_key UNIQUE,
           request jsonb, response jsonb, status, created_at)
```

`decisions` plus `decision_citations` plus `executions` is the audit trail. One
join answers "why was this paid, on whose authority, citing what" — which is the
question that gets asked in a year, by an auditor, about the one invoice that
turned out to be wrong.

## 13. Evals: the errors are not symmetric

The template ships an eval harness. Point it at decisions rather than answers, and
score the two error types separately, because they are not the same thing.

| Error | Cost |
|---|---|
| **False auto-approve** — approved something a human would have stopped | Money out the door. Unrecoverable trust |
| **False escalation** — queued something that was fine | Somebody clicks a button |

**CI gates on false auto-approves at zero on the labelled set.** False
escalations are a cost number, not a gate: they set the ROI, and the whole tuning
loop is lowering them while the first stays at zero.

The labelled set is 50-100 real documents per client with the decision a human
actually made, plus deliberate nasties: a duplicate invoice, one a cent over
threshold, a supplier not on the list, a scan that parses badly, a credit note,
an invoice in the wrong currency. Every production override gets added to the set.
That is what turns going live into the thing that improves it.

## 14. What goes back into the template

Decided up front, so it happens on purpose rather than being rediscovered on the
next project.

| Back to `templates/ai-project` | Stays in Docket |
|---|---|
| `collection` scoping on documents and retrieval | The invoice schema |
| Orgs, memberships, role-scoped access | Procurement rules |
| The extraction-with-provenance base classes and verbatim check | The adapters |
| The adapter Protocol and `DryRunAdapter` | The review-queue UI |
| Split-at-the-human-boundary approval pattern, as a documented pattern | |

Backport at the end of M3, once it has survived contact, not while it is still
moving.

## 15. App surface

Next.js, on the frontend the template already ships. Four routes, and only the
first one really matters.

- **`/queue` Review.** The product. Pending decisions, oldest first, amount and
  outcome badges, keyboard-first: `j`/`k` to move, `a` approve, `r` reject,
  `e` edit. A reviewer clearing forty invoices should never touch the mouse.
- **`/decisions/{id}`** Document on the left, extracted fields with their source
  spans in the middle, cited policy clauses on the right. Clicking a field
  highlights its span in the document; clicking a citation opens the clause.
  **This screen is the demo.** Build it first and build it well.
- **`/audit`** Everything, filterable, exportable. Boring, and the reason a
  finance director signs.
- **`/settings/rules`** Thresholds, approved suppliers, which rules may
  auto-approve, per-role approval limits.

Header stats: pending, decided today, auto-approved share, median time in queue,
override rate. The last two are the numbers that prove the thing works.

## 16. Milestones

**M1, the spike (a day).** No app, no queue. A script: one PDF in, extracted
schema with source spans out, verbatim check, and a decision citing a clause from
a policy markdown file. Answers the only question that matters cheaply — does
extraction plus policy retrieval hold up on real documents. If the spans do not
verify, stop and rethink before building a queue on top.

**M2, the pipeline (a weekend).** Migrations, `document.decide` and
`decision.execute` workflows, the router node, the repointed validator,
`DryRunAdapter`, `POST /decisions/{id}/approve`. API only, tested with pytest
against the template's existing conftest. Everything queues; nothing
auto-approves.

**M3, the app (a weekend).** Orgs and roles, the review queue, the decision
detail screen, the audit log, rules. Deploy to Railway. This is the point where
it is demoable.

**M4, earned.** Turn on auto-approve behind one narrow rule once the eval set
supports it. One real adapter. Email intake. Then a second schema — contract
renewals is the natural one — to prove the vertical really is configuration.

## 17. Risks

- **Extraction is fine on clean PDFs and bad on scans.** The likeliest way this
  disappoints in a real client's data. M1 exists to find that out for a day's
  work. Mitigation is failing loudly and queueing, never guessing.
- **The policy does not exist in writing.** Very common. Half the client's rules
  live in somebody's head. This turns discovery into a real workstream and it
  should be priced as one, because a policy corpus that does not exist cannot be
  retrieved.
- **The queue becomes as slow as the manual process.** If a reviewer has to
  re-read the invoice to trust the decision, nothing was saved. The detail screen
  earns its place here: the citation has to make the check take five seconds.
- **Scope creep toward a full AP product.** §4 is the spec. Approvals, not
  three-way matching, not a supplier portal.
- **One client's process quietly becomes the abstraction.** Guard by keeping the
  schema, rules and adapter genuinely swappable from M2, not by promising to
  refactor later.

## 18. Open decisions

1. **Name.** Docket is a working title. A docket is the list of matters awaiting
   decision, which is exactly right, and it may still be too courtroom.
2. **First vertical for the demo corpus.** Invoices per §3, or contract renewals,
   which have less crowded competition and are closer to what agencies and
   consultancies actually feel pain about.
3. **Whose documents does the demo run on?** A synthetic corpus that never
   embarrasses anyone, or a real prospect's with `DryRunAdapter`. The second sells
   far better and needs a signed sentence about data handling first.
4. **Does the reviewer see the model's rationale, or only the citations?** Showing
   the prose invites arguing with it. Showing only clauses is stricter and might
   be harder to trust. Probably citations first, rationale behind a disclosure.
5. **Email intake in v1 or not.** It is how documents actually arrive, and it is
   also a parsing surface with its own failure modes.
