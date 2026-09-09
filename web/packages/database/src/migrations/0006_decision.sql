-- The row the whole product is about.
--
-- A document arrives, the pipeline decides it against the organization's own
-- policy, and a human approves or overrides. Everything else here is in
-- service of being able to answer, a year later, why one invoice was paid.

create table if not exists "decision" (
  "id" text not null primary key,
  "organizationId" text not null references "organization" ("id") on delete cascade,

  -- No foreign keys yet: `sourceDocument` and `extraction` are still owned by
  -- the Python side and arrive in a later migration. Nullable until then.
  "documentId" text,
  "extractionId" text,

  -- `outcome` is what the pipeline decided. `status` is where the case has got
  -- to. They are separate because a reviewer can approve a decision whose
  -- outcome was `reject`, and the disagreement is the point: the original
  -- stays, the override sits beside it, and the gap between them is measurable
  -- per rule.
  "outcome" text not null,
  "status" text not null default 'pending_review',

  -- What the model proposed before the rails moved it. Two things need it: the
  -- override rate is the gap between this and `outcome`, and replay depends on
  -- it -- the rails are deterministic given their inputs, so a counterfactual
  -- rule can run over thousands of past decisions with no model calls, but only
  -- where the input was kept.
  "proposedOutcome" text,
  "rationale" text not null default '',
  "unmetConditions" text[] not null default '{}',
  -- Why the rails moved the outcome, in the reviewer's words. It is the first
  -- thing a reviewer needs to know, and deriving it later would mean re-running
  -- the decision.
  "railNotes" text[] not null default '{}',

  "ruleId" text,
  "groundingPassed" boolean not null default false,
  "groundingFailure" text,

  -- NULL means coverage was not checked, which is not the same as checked and
  -- found clean. The rail that reads it has to be able to tell those apart.
  "coverageComplete" boolean,
  "coverageRecall" numeric(4, 3),

  -- A cost centre or a role, never a person.
  "assignedTo" text,

  "decidedAt" timestamptz default CURRENT_TIMESTAMP not null,
  "reviewedBy" text references "user" ("id") on delete set null,
  "reviewedAt" timestamptz,
  "overrideOutcome" text,
  "overrideNote" text,
  "createdAt" timestamptz default CURRENT_TIMESTAMP not null,

  -- `status` is the pipeline's own vocabulary and is the same for every
  -- vertical, so naming its values here costs nothing.
  --
  -- `outcome` deliberately has no such constraint. Its values are the
  -- vertical's -- approve and route-to-cost-centre for invoices, something else
  -- for contract renewals -- and a check constraint listing them is what makes
  -- adding a document type a migration instead of configuration.
  constraint "decision_status_check" check (
    "status" in ('pending_review', 'approved', 'rejected', 'executed', 'failed')
  )
);

-- The queue: one organization's pending decisions, oldest first.
create index if not exists "decision_organizationId_status_decidedAt_idx"
  on "decision" ("organizationId", "status", "decidedAt");

alter table "decision" enable row level security;
alter table "decision" force row level security;
drop policy if exists "decision_org_isolation" on "decision";
-- No `app.worker` escape, unlike `apiKey` and `auditEntry`. Those need one
-- because they are read before the organization is known. Nothing reads a
-- decision without already knowing whose it is -- the pipeline learns the org
-- from the job it claimed, and hands it to `withOrgScopeFor`.
create policy "decision_org_isolation" on "decision"
  using ("organizationId" = current_setting('app.current_org', true))
  with check ("organizationId" = current_setting('app.current_org', true));

-- A policy clause that justified a decision, quoted verbatim.
create table if not exists "decisionCitation" (
  "id" text not null primary key,
  -- Carried rather than reached for through "decisionId". Row-level security
  -- filters one table at a time, so a citation without its own organization
  -- would be isolated only by the join that fetched it.
  "organizationId" text not null references "organization" ("id") on delete cascade,
  "decisionId" text not null references "decision" ("id") on delete cascade,
  -- Points into the chunk table Python owns. No foreign key: it crosses the
  -- ownership boundary, and it is nullable anyway because a decision can be
  -- grounded in an in-memory corpus. The excerpt and the clause reference are
  -- what an auditor reads either way.
  "chunkId" text,
  "documentId" text,
  "citationIndex" integer not null,
  "clauseRef" text not null,
  "excerpt" text not null
);

create index if not exists "decisionCitation_decisionId_idx"
  on "decisionCitation" ("decisionId", "citationIndex");

alter table "decisionCitation" enable row level security;
alter table "decisionCitation" force row level security;
drop policy if exists "decisionCitation_org_isolation" on "decisionCitation";
create policy "decisionCitation_org_isolation" on "decisionCitation"
  using ("organizationId" = current_setting('app.current_org', true))
  with check ("organizationId" = current_setting('app.current_org', true));
