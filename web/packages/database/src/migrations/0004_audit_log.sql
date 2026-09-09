-- Who did what, per organization.
--
-- Written by the auth middleware for every RPC that is not a read, so coverage
-- does not depend on anybody remembering to add a call. Denied attempts are
-- recorded too — an audit log that only contains successful actions cannot
-- answer the question people actually bring to it, which is whether somebody
-- tried something they should not have.
create table if not exists "auditEntry" (
  "id" text not null primary key,
  "organizationId" text not null references "organization" ("id") on delete cascade,
  "actorUserId" text not null,
  "actorEmail" text not null,
  "actorRole" text not null,
  "action" text not null,
  "outcome" text not null,
  -- Allowlisted payload fields only. See `auditableKeys` in the domain: a
  -- wholesale copy of the payload would have put an access token and a webhook
  -- signing secret in a table much of the organization can read.
  "detail" text not null default '',
  "at" timestamptz default CURRENT_TIMESTAMP not null,
  constraint "auditEntry_outcome_check" check ("outcome" in ('ok', 'denied', 'error'))
);

create index if not exists "auditEntry_organizationId_at_idx"
  on "auditEntry" ("organizationId", "at" desc);

alter table "auditEntry" enable row level security;
alter table "auditEntry" force row level security;
drop policy if exists "auditEntry_org_isolation" on "auditEntry";
create policy "auditEntry_org_isolation" on "auditEntry"
  using (
    "organizationId" = current_setting('app.current_org', true)
    or current_setting('app.worker', true) = 'on'
  )
  with check ("organizationId" = current_setting('app.current_org', true));
