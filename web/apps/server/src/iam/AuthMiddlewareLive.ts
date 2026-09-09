import { isReadOnlyAction } from "@forge/domain/iam/Audit";
import { AuthMiddleware } from "@forge/domain/iam/AuthMiddleware";
import { CurrentUser, Identity, OrgId, Unauthenticated, UserId } from "@forge/domain/iam/Identity";
import { Cause, Effect, Layer } from "effect";
import { AuditLog } from "./AuditLog.js";
import { Auth } from "./Auth.js";
import { PermissionResolver } from "./PermissionResolver.js";

/**
 * Turns request headers into a `CurrentUser`, and records what they did.
 *
 * A missing active organization is treated as unauthenticated rather than
 * defaulting to some org — silently picking one would be a tenancy bug.
 *
 * Auditing lives here rather than in each handler because this is the one place
 * every authenticated call already passes through. Coverage is therefore the
 * default: a new mutation is recorded without anybody adding a line to it, and
 * the only way to opt out is to name the endpoint like a read.
 */
export const AuthMiddlewareLive: Layer.Layer<
  AuthMiddleware,
  never,
  Auth | PermissionResolver | AuditLog
> = Layer.effect(
  AuthMiddleware,
)(
  Effect.gen(function*() {
    const auth = yield* Auth;
    const resolver = yield* PermissionResolver;
    const audit = yield* AuditLog;

    return AuthMiddleware.of((effect, options) =>
      Effect.gen(function*() {
        const session = yield* Effect.promise(() => auth.getSession(options.headers));

        if (session === null) {
          return yield* new Unauthenticated({ reason: "NoSession" });
        }

        const activeOrganizationId = session.session.activeOrganizationId;
        if (activeOrganizationId === null || activeOrganizationId === undefined) {
          return yield* new Unauthenticated({ reason: "NoActiveOrganization" });
        }

        // With dynamic access control an organization may define roles of its
        // own, so an unrecognised role is legitimate — it simply starts from no
        // permissions and gains whatever `organizationRole` grants it.
        const permissions = yield* resolver.resolve({
          organizationId: activeOrganizationId,
          memberId: session.session.memberId ?? "",
          role: session.session.role ?? "member",
        });

        const identity = new Identity({
          userId: UserId.make(session.user.id),
          orgId: OrgId.make(activeOrganizationId),
          email: session.user.email,
          emailVerified: session.user.emailVerified,
          role: session.session.role ?? "member",
          permissions,
        });

        const action = options.rpc._tag;

        if (isReadOnlyAction(action)) {
          return yield* Effect.provideService(effect, CurrentUser, identity);
        }

        /**
         * The outcome is part of the record. A denial is the most
         * security-relevant thing an audit log holds — somebody attempting
         * what their role does not allow — and a log of successes only cannot
         * show it.
         */
        return yield* Effect.provideService(effect, CurrentUser, identity).pipe(
          Effect.onExit((exit) =>
            audit.record({
              identity,
              action,
              outcome: exit._tag === "Success"
                ? "ok"
                : Cause.hasFails(exit.cause)
                ? "denied"
                : "error",
              payload: options.payload,
            })
          ),
        );
      })
    );
  }),
);
