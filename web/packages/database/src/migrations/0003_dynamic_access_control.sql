-- Dynamic access control and per-member permission overrides.
--
-- `organizationRole` is better-auth's, generated with `compileAuthMigrations`
-- after enabling `dynamicAccessControl`. It holds custom per-organization roles
-- whose permissions better-auth merges over the static roles at check time.

create table if not exists "organizationRole" (
  "id" text not null primary key,
  "organizationId" text not null references "organization" ("id") on delete cascade,
  "role" text not null,
  "permission" text not null,
  "createdAt" timestamptz default CURRENT_TIMESTAMP not null,
  "updatedAt" timestamptz
);

create index if not exists "organizationRole_organizationId_idx" on "organizationRole" ("organizationId");
create index if not exists "organizationRole_role_idx" on "organizationRole" ("role");

-- `memberPermission` is ours. It grants or revokes a single permission for one
-- member, on top of whatever their role already gives them.
--
-- `granted = false` is a revoke and wins over the role, so an owner can take
-- one capability away from an admin without inventing a whole new role.
create table if not exists "memberPermission" (
  "id" text not null primary key,
  "organizationId" text not null references "organization" ("id") on delete cascade,
  "memberId" text not null references "member" ("id") on delete cascade,
  "permission" text not null,
  "granted" boolean not null default true,
  "createdAt" timestamptz default CURRENT_TIMESTAMP not null,
  unique ("memberId", "permission")
);

create index if not exists "memberPermission_memberId_idx" on "memberPermission" ("memberId");

alter table "memberPermission" enable row level security;
alter table "memberPermission" force row level security;

drop policy if exists "memberPermission_org_isolation" on "memberPermission";
create policy "memberPermission_org_isolation" on "memberPermission"
  using ("organizationId" = current_setting('app.current_org', true))
  with check ("organizationId" = current_setting('app.current_org', true));
