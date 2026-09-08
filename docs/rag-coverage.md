# Coverage-checked retrieval, and the eval that measures it

Built 7 September 2026. Two things: a retrieval layer that cannot silently
miss a policy rule that applies, and a harness that measures whether that
is true.

## The problem

Top-k retrieval fails in two ways and only one is visible.

It can return something irrelevant. Everything downstream catches that: the
excerpt will not be verbatim, or the judge rejects it, or a reviewer reads
it and frowns.

It can fail to return something relevant. **Nothing catches that.** The
verbatim check, the judge and the reviewer all inspect what came back; none
can see what did not. The decision arrives confident, correctly cited, and
silent about the rule nobody asked.

M1 hit exactly this: a USD invoice never retrieved "invoices are payable in
euro", so the model compared 8,400 USD against euro thresholds and said
nothing about the currency. Nothing failed. The output looked correct.

A missed clause is indistinguishable from a satisfied one. No amount of
better ranking fixes it, because ranking cannot tell you what it did not
rank. The M1 fix, stuffing policy vocabulary into the query, made that
particular case work and left the class of bug wide open.

## The approach

Stop treating the policy as a pile of text to search, and index it once as
what it is: a set of obligations, each governing one dimension of the
document being judged, each tied to the clause that states it.

At decision time:

1. **Compute which obligations apply**, in code, from the extracted fields.
   No model, no retrieval. A USD invoice triggers `currency` because its
   currency field is not EUR, not because a query happened to contain the
   right word.
2. **Retrieve as normal.** Ranking is still what finds the most relevant
   clauses.
3. **Repair, do not report.** Any triggered obligation whose clause ranking
   missed is fetched directly by id and added to the evidence *before the
   model sees anything*. A warning about a missed clause only helps whoever
   reads logs; the decision is about to be made either way.
4. **Escalate only what cannot be repaired** — an obligation whose clause
   was deleted or never chunked. Rail 1b turns that into `needs_human`.

The model builds the index, once, at ingest. It does not get to decide at
decision time whether a rule was relevant; that check runs in code against
stored rows a client can read and edit.

What this buys, beyond correctness, is the claim. "We searched the policy
and here is what came back" is what every RAG system can say. "These seven
rules applied to this invoice and every one of them was considered" is a
different and much stronger thing, and it is what an approval product is
actually selling.

## Where it lives

| | |
|---|---|
| `app/decisions/coverage.py` | Dimensions, obligations, triggers, the check |
| `app/decisions/policy.py` | `CoveredPolicy`, the repairing wrapper |
| `app/db/models.py` | `PolicyObligation`, migration 0007 |
| `app/workflows/document_ingest.py` | `IndexObligations`, runs for policy documents only |
| `app/decisions/rails.py` | Rail 1b: an unrepairable gap forces review |
| `evals/run_decision_eval.py` | Recall, the two error types, stability |

## Also landed

**Voyage embeddings** (`voyage-3.5`, 1024 dimensions, migration 0006).
Anthropic has no embeddings API, so the provider is chosen separately; Voyage
distinguishes query embeddings from document embeddings, which retrieval now
uses (`embed_query` vs `embed_documents`). Migration 0006 keeps every chunk
and every citation and only clears the vectors, because
`decision_citations.chunk_id` points at chunks and the audit trail does not
get damaged by a model upgrade. `scripts/reembed.py` refills them.

**Contextual retrieval** (`app/ingestion/context.py`). A chunk that reads
"This does not apply to intercompany recharges" is about nothing once it is
separated from its heading. Two strategies: `structural` (document name plus
heading path, free, and for a policy corpus it is most of the benefit
because a policy's headings are its context) and `llm` (a generated sentence
per chunk, closer to the published technique). Only the embedded text is
contextualized; stored content stays exactly as written, because a citation
quotes the document, not our summary of it.

## What the eval says

Five cases, three runs, fifteen decisions:

```
outcome matches      4/15
grounded             9/15
mean recall          1.000
false escalations    3/15   (cost, not a gate)
FALSE AUTO-APPROVES  0/15   (gate: must be 0)
```

**Recall is 1.000.** Coverage repair works, and the M1 currency case is
fixed by construction rather than by prompt wording. That is the RAG result.

**Everything else says the problem was never retrieval.** Grounding passes
on 9 of 15, outcomes match on 4 of 15, and two of five cases give different
answers on different runs. The judge, not the retriever, is what stands
between this and a usable escalation rate.

## Two things the harness got wrong first, and why they matter

**The gate was vacuous.** The first version passed no rule to `apply_rails`,
so rail 3 blocked every auto-approve and "zero false auto-approves" was true
because the failure was impossible, not because it was avoided. It printed a
confident PASS. It now arms a rule and refuses to run without one.

**It is still not proven.** Even armed, no decision reached `auto_approve`
in any run, because the model never proposes it against a policy whose every
clause names an approver. The harness says so out loud rather than showing a
green tick: *armed and untested is not the same as passing*. Exercising it
needs a negative-control case, or a policy that authorises unattended
payment.

## Next

`--runs N` exists because every prompt change before today was measured on a
single five-document run, which is an anecdote. Two of five cases are
unstable across three runs, so any change that moves one case proves
nothing.

The order that follows from the numbers: fix grounding, not retrieval.
Recall is at ceiling and the judge is rejecting 40 percent of decisions.
Start by looking at what it rejects, with `--runs 5` as the measurement.

---

## Update, 8 September 2026: what a real corpus revealed

Voyage embeddings and the seven-document corpus went in together, so hybrid
retrieval ran for the first time and coverage checking met a corpus with
more than one policy in it. Both changed the picture.

**Retrieval ranks correctly and the distractors sit right behind it.** On
"is a purchase order required above EUR 500?", the current policy takes
ranks 1 and 2 and the *superseded 2024 policy* takes 3 and 4, carrying the
old EUR 1,000 threshold. That is a different failure from the one coverage
fixes: coverage catches a relevant clause that was not retrieved, this is an
irrelevant one that was. The grounding judge is what has to catch it, and
now there is a corpus where it can be tested.

**Coverage was requiring rules from every policy in the org.** The check
loaded all 130 obligations regardless of which document they came from, so
a supplier invoice was being checked against expense-claim thresholds, capex
approval limits, and a superseded policy's spend bands — and the repair step
faithfully fetched all of those clauses into the evidence before the model
decided. It made decisions worse, and no single-document corpus could ever
have shown it.

Obligations now carry `schema_name` and `in_force` (migration 0008),
extracted with the document title in context because "up to EUR 1,500: the
line manager may approve" reads identically whether it governs invoices or
expense claims. After re-indexing:

| document | obligations | govern invoices |
|---|---|---|
| procurement-policy.md | 27 | 27 |
| delegation-of-authority.md | 20 | 19 |
| approved-suppliers.md | 10 | 10 |
| contracting-standards.md | 7 | 5 |
| capital-expenditure.md | 7 | **0** |
| procurement-policy-2024-superseded.md | 2 | **0** |
| travel-and-expenses.md | 0 | **0** |

Repair dropped from 15 clauses to 8 and the dangerous documents are out.

## The next problem, precisely

The eight clauses repair still pulls in are the delegation matrix's
per-category ladders: Telecoms, Office Consumables, Catering, Legal
Services, and so on, fetched for a *cleaning* invoice.

They are not wrong to be obligations. They genuinely govern invoices, they
are in force, and they are `amount` rules. The trouble is that `Dimension`
is too coarse to express "this rule governs invoices **for telecoms**". Every
invoice triggers `amount`, so every category ladder is required, every time.

This is a modelling limit rather than a bug, and the fix is real work:
obligations need applicability conditions of their own — a category, a
supplier, a cost centre — evaluated against the extracted fields the same
way the dimension triggers already are. That is the natural next step for
`coverage.py`, and it is worth doing before the escalation rate means
anything, because eight irrelevant clauses in the evidence is a good way to
make a judge reject a citation.
