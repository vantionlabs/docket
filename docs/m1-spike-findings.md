# M1 spike findings

Run 6 September 2026, against `claude-sonnet-5` via the template's provider
seam, on five fixture invoices and a 10-clause procurement policy.

The spike answers one question (spec section 16): does extraction with
source spans, plus a policy check, hold up on real documents? If the spans
do not verify, stop and rethink before building a queue on top.

## The answer

**Spans verified on 5 of 5 documents.** Every extracted field quoted text
that was really on the page, under whitespace-normalized, case-insensitive
matching. Nothing else is normalized, so punctuation, digits and currency
symbols had to match exactly. Go ahead and build M2.

That result comes from clean generated markdown. It says the approach is
sound. It does not say anything yet about scans, which is risk 1 in section
17 and still needs real client documents.

## What went right

- Arithmetic caught in code, not by the model. Fixture 04 states a subtotal
  of 1818.00 while its lines sum to 1518.00, and an implied VAT rate of
  17.53 percent. Both were caught before the model saw the invoice, and both
  were handed to it as warnings, which is why it rejected on the right
  grounds.
- Citations were verbatim in every run. The structural check never had to
  reject one, though the tests prove it does when given a paraphrase.
- The refusal behaved. Fixture 03, an unknown supplier, routed to
  Procurement citing the clause that says to. Fixture 02, no PO and over
  threshold, named both failures separately rather than merging them.

## What went wrong, and what changed

**A missed clause looks exactly like a satisfied one.** Fixture 05 is
denominated in USD. The first run never retrieved clause 8, "Invoices are
payable in euro", so the model compared 8400 USD against euro thresholds
and said nothing about the currency. Nothing failed. The output looked
correct and was not.

The cause was the query, not the retriever: it was built from the invoice's
values ("amount 8400.0 USD") and the clause is written in the policy's words
("euro", "another currency"). They share no token.

`invoice_query` now names the dimensions policy cares about, whether or not
the invoice happens to use the policy's vocabulary: a standing list of
threshold, supplier list, PO requirement, payment terms, currency, VAT rate
and duplicates, plus conditional phrasing for a non-euro invoice and for
shortened payment terms. Clause 8 is now retrieved and cited, and the model
adds that the approval tier must be reconfirmed after conversion.

Two tests pin this (`test_non_euro_invoice_retrieves_the_currency_clause`,
`test_standing_dimensions_are_always_asked`).

**This is the failure mode to design against in M2.** The rails catch a
decision that cites badly. Nothing catches a decision that was never asked
the right question. Retrieval recall on the policy corpus is a first-class
eval metric, not a tuning detail.

## An honest note on auto-approve

Nothing auto-approved, even with the rule armed, because the model never
proposed `auto_approve` against this corpus. It is right not to: every
clause in the policy names an approver, so no policy text authorises acting
without one.

That is the correct division of labour and it matches section 9 rail 3. The
policy says who may approve. The *rule* says whether that approval can be
presumed for a narrow, evidenced class of invoice. Auto-approve is a
configuration decision backed by the eval set, never something the model
talks itself into. The rails tests cover the gate opening and closing.

## Cost

Five documents, two model calls each (extraction, decision). Recorded
through `record_usage` under the `extraction` and `decision` operations, so
it lands in the same cost log as chat and grounding.

## Not in the spike, on purpose

- The LLM judge on citations. The structural check answers M1's question,
  and the judge is M2 with the rest of the pipeline.
- pgvector. Policy retrieval is lexical and in-memory here; M2 swaps
  `PolicyCorpus.retrieve` for `hybrid_search(..., collection="policy")` and
  nothing above it changes.
- PDFs. `parse_document` already handles them with the docling extra. The
  fixtures are markdown so the spike runs without pulling torch.
