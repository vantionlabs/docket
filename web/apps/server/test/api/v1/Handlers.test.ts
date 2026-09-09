import { NodeHttpPlatform, NodeServices } from "@effect/platform-node";
import { PgLive } from "@forge/database/PgLive";
import { PgPoolTest, testDbUrl } from "@forge/database/PgTest";
import { ApiV1 } from "@forge/domain/api/v1/Api";
import { KEY_PREFIX } from "@forge/domain/iam/ApiKey";
import { ApiKeyAuth } from "@forge/server/api/ApiKeyAuth";
import { ApiV1Live } from "@forge/server/api/v1/Handlers";
import { ContactStore } from "@forge/server/contact/ContactStore";
import { PermissionResolver } from "@forge/server/iam/PermissionResolver";
import { Effect, Layer } from "effect";
import { Etag, HttpRouter } from "effect/unstable/http";
import { HttpApiBuilder } from "effect/unstable/httpapi";
import { SqlClient } from "effect/unstable/sql";
import { createHash, randomBytes, randomUUID } from "node:crypto";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

/**
 * The real API, over the real database, with only the transport swapped.
 *
 * `provideRequest` rather than `provide` for ApiKeyAuth: a route's requirements
 * are per-request, so the service has to reach each request's context — which is
 * what `serve` does for the running server.
 */
const Sql = PgLive.pipe(Layer.provideMerge(PgPoolTest));

const app = HttpRouter.toWebHandler(
  HttpApiBuilder.layer(ApiV1).pipe(
    Layer.provide(ApiV1Live.pipe(Layer.provide(ContactStore.layer), Layer.provide(Sql))),
    HttpRouter.provideRequest(
      ApiKeyAuth.layer.pipe(Layer.provide(PermissionResolver.layer), Layer.provide(Sql)),
    ),
    Layer.provide(Etag.layer),
    Layer.provide(NodeHttpPlatform.layer),
    Layer.provide(NodeServices.layer),
  ),
  { disableLogger: true },
);

/** Mints a key straight into the table, the way the RPC handler would. */
const seedKey = (org: string, role: string) =>
  Effect.gen(function*() {
    const sql = yield* SqlClient.SqlClient;
    const key = `${KEY_PREFIX}${randomBytes(32).toString("hex")}`;
    const hash = createHash("sha256").update(key).digest("hex");

    yield* sql`
      insert into "organization" ("id", "name", "slug", "createdAt")
      values (${org}, ${org}, ${org}, now()) on conflict do nothing
    `;
    yield* sql`
      insert into "apiKey" ("id", "organizationId", "name", "hash", "hint", "role")
      values (${randomUUID()}, ${org}, 'test', ${hash}, ${key.slice(11, 19)}, ${role})
    `;

    return key;
  });

const call = (key: string | undefined, path: string, init?: RequestInit) =>
  app.handler(
    new Request(`http://localhost/api/v1${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(key === undefined ? {} : { authorization: `Bearer ${key}` }),
      },
    }),
  );

describe.skipIf(testDbUrl() === undefined)("v1 contacts", () => {
  const orgA = `org_a_${randomUUID().slice(0, 8)}`;
  const orgB = `org_b_${randomUUID().slice(0, 8)}`;
  let owner = "";
  let member = "";
  let other = "";

  beforeAll(async () => {
    const run = <A>(effect: Effect.Effect<A, unknown, SqlClient.SqlClient>) =>
      Effect.runPromise(
        effect.pipe(Effect.provide(Layer.provide(PgLive, PgPoolTest))) as Effect.Effect<A>,
      );

    owner = await run(seedKey(orgA, "owner"));
    member = await run(seedKey(orgA, "member"));
    other = await run(seedKey(orgB, "owner"));
  });

  afterAll(() => app.dispose());

  it("refuses a request with no key, a malformed key and an unknown one alike", async () => {
    expect((await call(undefined, "/contacts")).status).toBe(401);
    expect((await call("nonsense", "/contacts")).status).toBe(401);
    expect((await call(`${KEY_PREFIX}${"a".repeat(64)}`, "/contacts")).status).toBe(401);
  });

  it("creates and lists in the wire shape, not the domain's", async () => {
    const created = await call(owner, "/contacts", {
      method: "POST",
      body: JSON.stringify({ email: "ada@example.com", full_name: "Ada Lovelace" }),
    });

    expect(created.status).toBe(201);
    expect(await created.json()).toMatchObject({
      email: "ada@example.com",
      full_name: "Ada Lovelace",
    });
  });

  /** A key gets exactly what its role grants — `member` cannot delete. */
  it("enforces the role's permissions and names the missing one", async () => {
    const created = await (await call(owner, "/contacts", {
      method: "POST",
      body: JSON.stringify({ email: "grace@example.com", full_name: "Grace Hopper" }),
    })).json() as { id: string; };

    const refused = await call(member, `/contacts/${created.id}`, { method: "DELETE" });

    expect(refused.status).toBe(403);
    expect(await refused.json()).toMatchObject({
      message: "This key's role lacks contact:delete.",
    });
  });

  /**
   * The property the whole public surface rests on. A key is scoped to one
   * organization, and this is a second front door onto the same data — so it has
   * to isolate as hard as the RPC one does.
   */
  it("shows one organization nothing of another's, and cannot delete across", async () => {
    const created = await (await call(owner, "/contacts", {
      method: "POST",
      body: JSON.stringify({ email: "hedy@example.com", full_name: "Hedy Lamarr" }),
    })).json() as { id: string; };

    const theirs = await (await call(other, "/contacts")).json() as ReadonlyArray<unknown>;
    expect(theirs).toEqual([]);

    // 404 rather than 403: to this key the row does not exist at all.
    expect((await call(other, `/contacts/${created.id}`, { method: "DELETE" })).status).toBe(404);
    expect((await call(owner, `/contacts/${created.id}`, { method: "DELETE" })).status).toBe(204);
  });

  it("answers 404 for a delete that matched nothing", async () => {
    expect((await call(owner, `/contacts/${randomUUID()}`, { method: "DELETE" })).status).toBe(404);
  });
});
