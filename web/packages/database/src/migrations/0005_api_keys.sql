-- Credentials for calling the app without a browser session.
create table if not exists "apiKey" (
  "id" text not null primary key,
  "organizationId" text not null references "organization" ("id") on delete cascade,
  "name" text not null,
  -- SHA-256 of the key. A dump of this table must not be a set of working
  -- credentials, for the same reason passwords are not stored. Unsalted is
  -- deliberate: the input is 32 bytes of CSPRNG output, so there is no
  -- dictionary to attack.
  "hash" text not null,
  -- Held in clear so a leaked key can be identified and revoked. A credential
  -- nobody can point at is a credential nobody can turn off.
  "hint" text not null,
  -- The role the key acts as. Scoped to a role rather than to its creator, so it
  -- cannot silently gain capabilities when that person is promoted, nor keep
  -- them after they leave.
  "role" text not null default 'member',
  "createdAt" timestamptz default CURRENT_TIMESTAMP not null,
  "lastUsedAt" timestamptz
);

-- The lookup on every API request: by hash, and nothing else.
create unique index if not exists "apiKey_hash_key" on "apiKey" ("hash");
create index if not exists "apiKey_organizationId_idx" on "apiKey" ("organizationId");

alter table "apiKey" enable row level security;
alter table "apiKey" force row level security;
drop policy if exists "apiKey_org_isolation" on "apiKey";
-- The `using` escape matters more here than elsewhere: authenticating a request
-- means finding a key before any organization is known, which is precisely a
-- cross-tenant read. Writes stay scoped, so a key can only ever be created
-- inside the organization that owns it.
create policy "apiKey_org_isolation" on "apiKey"
  using (
    "organizationId" = current_setting('app.current_org', true)
    or current_setting('app.worker', true) = 'on'
  )
  with check ("organizationId" = current_setting('app.current_org', true));
