import type { Array as Arr } from "effect";
import { Effect, Schema } from "effect";
import { CurrentUser, type Identity } from "./Identity.js";
import type { Permission } from "./Permission.js";

/**
 * The caller is authenticated but not allowed to do this. Distinct from
 * `Unauthenticated`, which means we do not know who they are — conflating the
 * two makes it impossible for a client to tell "sign in" from "ask an admin".
 */
export class Forbidden extends Schema.TaggedError<Forbidden>()("Forbidden", {
  required: Schema.String,
}) {}

/**
 * An access rule evaluated against the caller: succeeds with void, or fails
 * `Forbidden`. Because it is an ordinary Effect it composes with everything
 * else — no separate guard mechanism to learn.
 */
export type Policy<E = never, R = never> = Effect.Effect<void, Forbidden | E, CurrentUser | R>;

/** Builds a policy from a predicate over the caller. */
export const policy = <E, R>(
  required: string,
  predicate: (identity: Identity) => Effect.Effect<boolean, E, R>,
): Policy<E, R> =>
  Effect.flatMap(
    CurrentUser,
    (identity) =>
      Effect.flatMap(predicate(identity), (allowed) =>
        allowed ? Effect.void : Effect.fail(new Forbidden({ required }))),
  );

/** Runs the policy first, and only then the effect it guards. */
export const withPolicy =
  <E, R>(self: Policy<E, R>) => <A, E2, R2>(guarded: Effect.Effect<A, E2, R2>) =>
    Effect.andThen(self, guarded);

/** Every policy must pass. */
export const all = <E, R>(...policies: Arr.NonEmptyReadonlyArray<Policy<E, R>>): Policy<E, R> =>
  Effect.all(policies, { concurrency: 1, discard: true });

/** At least one policy must pass. */
export const any = <E, R>(...policies: Arr.NonEmptyReadonlyArray<Policy<E, R>>): Policy<E, R> =>
  Effect.firstSuccessOf(policies);

/** The common case: does the caller's role carry this permission? */
export const permission = (required: Permission): Policy =>
  policy(required, (identity) => Effect.succeed(identity.permissions.includes(required)));
