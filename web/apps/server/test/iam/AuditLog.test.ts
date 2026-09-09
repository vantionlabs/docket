import { describe, expect, it } from "@effect/vitest";
import { PgLive } from "@forge/database/PgLive";
import { PgPoolTest, testDbUrl } from "@forge/database/PgTest";
import { Identity, OrgId, UserId } from "@forge/domain/iam/Identity";
import { permissionsFor } from "@forge/domain/iam/Permission";
import { AuditLog } from "@forge/server/iam/AuditLog";
import { Effect, Layer } from "effect";
import { SqlClient } from "effect/unstable/sql";

const ORG = "org_audit";

const identity = new Identity({
  userId: UserId.make("user_audit"),
  orgId: OrgId.make(ORG),
  email: "auditor@example.com",
  emailVerified: true,
  role: "owner",
  permissions: Array.from(permissionsFor("owner")),
});

const live = AuditLog.layer.pipe(Layer.provideMerge(PgLive), Layer.provideMerge(PgPoolTest));

const reset = Effect.fnUntraced(function*() {
  const sql = yield* SqlClient.SqlClient;

  yield* sql`insert into "organization" ("id", "name", "slug", "createdAt")
             values (${ORG}, ${ORG}, ${ORG}, now()) on conflict ("id") do nothing`;
  yield* sql`delete from "auditEntry" where "organizationId" = ${ORG}`;
});

const entries = Effect.fnUntraced(function*() {
  const sql = yield* SqlClient.SqlClient;

  return yield* sql<{ action: string; outcome: string; detail: string; actorEmail: string; }>`
    select "action", "outcome", "detail", "actorEmail" from "auditEntry"
    where "organizationId" = ${ORG} order by "at"
  `;
});

describe.skipIf(testDbUrl() === undefined)("AuditLog", () => {
  it.layer(live)("recording", (it) => {
    it.effect("writes the actor, the action and the allowlisted fields", () =>
      Effect.gen(function*() {
        const audit = yield* AuditLog;

        yield* reset();
        yield* audit.record({
          identity,
          action: "CreateContact",
          outcome: "ok",
          payload: { name: "Ada Lovelace", role: "member" },
        });

        const [entry] = yield* entries();
        expect(entry?.action).toBe("CreateContact");
        expect(entry?.outcome).toBe("ok");
        expect(entry?.actorEmail).toBe("auditor@example.com");
        expect(entry?.detail).toContain("name=Ada Lovelace");
        expect(entry?.detail).toContain("role=member");
      }));

    /**
     * The reason the allowlist exists. This payload is exactly the shape of a
     * real integration-connect call, and the log is readable by anyone holding
     * `member:read`.
     */
    it.effect("never writes a credential into a table others can read", () =>
      Effect.gen(function*() {
        const audit = yield* AuditLog;

        yield* reset();
        yield* audit.record({
          identity,
          action: "ConnectIntegration",
          outcome: "ok",
          payload: { token: "pat-eu1-a-real-looking-token" },
        });

        const [entry] = yield* entries();
        expect(entry?.action).toBe("ConnectIntegration");
        expect(entry?.detail).toBe("");
        expect(entry?.detail).not.toContain("pat-eu1");
      }));

    it.effect("records a refusal, which is the row that matters most", () =>
      Effect.gen(function*() {
        const audit = yield* AuditLog;

        yield* reset();
        yield* audit.record({
          identity,
          action: "DeleteOrganization",
          outcome: "denied",
          payload: { confirmName: "Someone Else" },
        });

        expect((yield* entries())[0]?.outcome).toBe("denied");
      }));

    /**
     * A failing audit write must not fail the action it describes: refusing a
     * work because its log row would not insert is worse than the missing
     * row. An organization that does not exist violates the foreign key, which
     * is the easiest way to make the insert fail for real.
     */
    it.effect("succeeds even when the write itself cannot happen", () =>
      Effect.gen(function*() {
        const audit = yield* AuditLog;

        yield* reset();
        yield* audit.record({
          identity: new Identity({ ...identity, orgId: OrgId.make("org_does_not_exist") }),
          action: "CreateCampaign",
          outcome: "ok",
          payload: {},
        });

        // No throw, and nothing written for the real organization either.
        expect(yield* entries()).toHaveLength(0);
      }));
  });
});
