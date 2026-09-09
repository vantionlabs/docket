import { Effect, Ref, Schedule, Stream } from "effect";

/**
 * How hard to try to get back.
 *
 * Jittered on purpose, and not as a flourish. Every browser watching a server
 * loses its stream at the same instant — a deploy, a restart — so an unjittered
 * backoff brings all of them back in lockstep, repeatedly, at exactly the moment
 * the server is least able to take it.
 *
 * `min` of an exponential and a fixed spacing is a capped exponential: quick at
 * first, then settling at thirty seconds and staying there. There is no attempt
 * limit because there is no such thing as giving up on a live connection — a
 * laptop can be shut for a weekend and must still come back.
 */
export const defaultBackoff: Schedule.Schedule<unknown> = Schedule.min([
  Schedule.exponential("1 second"),
  Schedule.spaced("30 seconds"),
]).pipe(Schedule.jittered);

/**
 * Keeps a subscription open across disconnections.
 *
 * Both endings are handled, because a lost connection can present as either. A
 * transport error fails the stream, which `retry` restarts; a peer that closes
 * cleanly ends it, which `repeat` restarts. Handling only the first would leave a
 * silent permanent stall behind the more ordinary of the two.
 *
 * `onReconnect` runs before every attempt except the first, and it is the reason
 * reconnecting is worth anything. Whatever happened while the connection was down
 * was missed — a live subscription has no replay — so a fresh one has to assume
 * it is behind rather than assume it is current. The first attempt is exempt
 * because nothing has been missed yet, and treating it like a reconnect would
 * cost every page load a second round trip.
 *
 * Returns an `Effect` rather than a `Stream` because the first-attempt flag has
 * to be allocated once per held connection, not once per attempt.
 */
export const holdOpen = <A, E, R>(options: {
  /** Called again for each attempt, so it must build a fresh subscription. */
  readonly open: () => Stream.Stream<A, E, R>;
  readonly onReconnect: Effect.Effect<void>;
  /** Output type is free — only the delays matter here. */
  readonly backoff?: Schedule.Schedule<unknown> | undefined;
}): Effect.Effect<Stream.Stream<A, E, R>> =>
  Effect.gen(function*() {
    const backoff = options.backoff ?? defaultBackoff;
    const connectedBefore = yield* Ref.make(false);

    const attempt = Stream.unwrap(Effect.gen(function*() {
      if (yield* Ref.getAndSet(connectedBefore, true)) yield* options.onReconnect;

      return options.open();
    }));

    return attempt.pipe(Stream.retry(backoff), Stream.repeat(backoff));
  });
