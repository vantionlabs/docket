# Roadmap

Where Docket is, and what is left. Ordered so that each milestone unblocks
the next rather than by how interesting it is.

Done: M1 the spike, M2 the pipeline, M3 the app, plus intake, coverage-checked
retrieval, the backport, and the test corpus. See the notes in this folder.

---

## M4 — Make the measurement trustworthy

Everything downstream is tuning, and tuning against a noisy instrument is
worse than not tuning. Three things stand between here and a number worth
acting on.

**M4.1 Obligation applicability.** `Dimension` cannot express "governs
invoices *for telecoms*", so every invoice triggers `amount` and all fifteen
of the delegation matrix's category ladders get required and repaired into
the evidence. Eight irrelevant clauses per decision is a good way to make a
judge reject a citation. Obligations need conditions of their own —
category, supplier, cost centre — evaluated against the extracted fields the
way dimension triggers already are.

**M4.2 A held-out split.** All 150 labelled invoices are one pool. Tuning
against all of them and reporting on all of them measures nothing. Tune on
~100, keep ~50 unseen until the end.

**M4.3 Langfuse verified.** Configured, never confirmed. Per-call traces are
worth having *before* the judge work, not after, because the question will be
"which citation did it reject and why".

## M5 — Fix the grounding judge

The eval says recall is at ceiling and grounding passes on 9 of 15. The
judge, not the retriever, is what caps the escalation rate. With M4 done,
run the labelled set (~450 calls), read what it rejects, change one thing,
re-run against the training split only. The held-out set is scored once, at
the end.

Section 13's gate stays: false auto-approves at zero. False escalation is
the number being driven down.

## M6 — Turn on auto-approve

Only once M5 says a narrow rule is safe. One rule, one narrow band, and the
eval gate exercised for real rather than armed and untested.

## M7 — Ship it

**M7.1 A real adapter.** Only `DryRunAdapter` and `EmailAdapter` exist.
**M7.2 Railway deploy.** Listed under M3 in the spec and never done.
**M7.3 Bucket CORS.** Browser uploads need `PUT` allowed from the app origin.

## M8 — Prove the vertical is configuration

Contract renewals as a second schema, per spec section 16. The schema
registry and the collection scoping are the seams it plugs into. If this
takes a day rather than a fork, the claim in section 3 holds.

---

## Not scheduled, and worth saying

- **Reranking** is built, off, never tuned. It needs no key. Worth an hour
  once the eval is trustworthy, and worthless before then.
- **Approval chains.** Two sequential approvals are two rows and two events
  today. Fine at this size (spec section 6).
- **Org switching.** One org per user; `active_membership` is the only
  function that has to change.
