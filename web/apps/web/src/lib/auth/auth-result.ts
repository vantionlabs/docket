import { Option } from "effect";
import { AsyncResult } from "effect/unstable/reactivity";

type Failure = { readonly _tag: string; readonly reason?: string; };

const failure = (result: AsyncResult.AsyncResult<unknown, Failure>) => AsyncResult.error(result);

/**
 * The typed error lives in the result's `Cause`, so it is read through
 * `AsyncResult.error` rather than off the result directly.
 */
export const isRateLimited = (result: AsyncResult.AsyncResult<unknown, Failure>) =>
  Option.match(failure(result), {
    onNone: () => false,
    onSome: (error) => error._tag === "SignInFailed" && error.reason === "RateLimited",
  });

/**
 * A failed submit is either the form not validating or the request being
 * rejected — telling someone their password was wrong when they simply left a
 * field blank sends them looking in the wrong place.
 */
export const isInvalidForm = (result: AsyncResult.AsyncResult<unknown, Failure>) =>
  Option.match(failure(result), {
    onNone: () => false,
    onSome: (error) => error._tag !== "SignInFailed",
  });

/** Picks the message for a form-level alert. `rejected` is the request-level case. */
export const submitMessage = (
  result: AsyncResult.AsyncResult<unknown, Failure>,
  rejected: string,
) =>
  isInvalidForm(result)
    ? "Check the fields above and try again."
    : isRateLimited(result)
    ? "Too many attempts. Try again in a minute."
    : rejected;
