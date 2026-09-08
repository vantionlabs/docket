# M5 baseline: the judge was a third of the problem

99 labelled invoices, training split, run against the real pipeline
(`--live`): the database corpus, Voyage embeddings, scoped obligations.

```
outcome matches        7/99
grounded              33/99
mean recall            1.000
false escalations     27/99   (cost, not a gate)
FALSE AUTO-APPROVES    0/99   (gate never exercised)
```

## The distribution is the finding

Sixty-six grounding failures, by cause:

| count | cause | kind |
|---:|---|---|
| 26 | judge rejected citations | judgement |
| 25 | markers without citations | bookkeeping |
| 13 | cites a clause not offered | bookkeeping |
| 2 | excerpt not verbatim | bookkeeping |

**Forty of sixty-six are bookkeeping, not judgement.** The model writes `[7]`
in its rationale and supplies no entry for 7. One case wrote fourteen
markers. That is not the judge disagreeing about whether a clause supports a
claim; it is the model losing track of its own numbering, and the system
treating a clerical slip as a grounding failure.

M5 was planned as "fix the judge" on the strength of 9/15 grounded from an
earlier run. The judge is real and it is 26 of 66. It is not the headline.

## Why the numbering drifts

`Decision` declared `rationale` before `citations`. Structured output is
generated in declaration order, so the model wrote the entire rationale,
with every `[n]` marker in it, **before writing a single citation**. It was
committing to numbering it had not yet chosen, then reverse-engineering a
citation list to match.

Reordering so citations come first — choose and number the clauses, then
write prose referring to numbers already committed to — costs nothing and
is the obvious shape. Paired with an instruction to cite at most six and
keep the rationale short, since a rationale with fourteen markers is one
that has lost track of itself.

## Recall is not the problem and has not been for some time

1.000 across all 99. Coverage checking does what it claims: every rule that
applies is in front of the model. Three consecutive rounds of work have now
moved the failure elsewhere each time — first to retrieval noise, then to
attribution, now to citation bookkeeping. That is what a working measurement
loop looks like.

## The gate is still untested

No decision reached `auto_approve` in 99 cases, so zero false auto-approvals
means the failure never had the opportunity to occur. The harness says so
rather than showing a green tick. Exercising it properly needs a negative
control, or a policy that authorises unattended payment.

## Cost

$4.78 for the 99-case run, on OpenRouter through
`anthropic/claude-sonnet-5` with `anthropic/claude-haiku-4.5` grounding.
About five cents a decision, three model calls each.
