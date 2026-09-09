import { holdOpen } from "@/atom/hold-open.js";
import { Effect, Ref, Schedule, Stream } from "effect";
import { describe, expect, it } from "vitest";

/** No waiting: the backoff itself is not what these assert. */
const instant = Schedule.spaced("0 millis");

/**
 * Keeping a live subscription alive across a disconnect.
 *
 * Every failure here is invisible from outside. A stream that stopped reopening
 * looks exactly like a quiet day, and a stream that reopens without catching up
 * looks exactly like a working one — the page simply stays wrong, with no error
 * anywhere. So both halves are pinned: that it comes back, and that it knows it
 * missed something when it does.
 */
describe("holdOpen", () => {
  it("reopens after the connection fails", async () => {
    const attempts = await Effect.runPromise(Effect.gen(function*() {
      const opened = yield* Ref.make(0);

      const stream = yield* holdOpen({
        backoff: instant,
        onReconnect: Effect.void,
        open: () =>
          Stream.unwrap(Effect.gen(function*() {
            const attempt = yield* Ref.updateAndGet(opened, (n) => n + 1);

            // Emits its attempt number, then drops the connection.
            return Stream.make(attempt).pipe(
              Stream.concat(Stream.fail(new Error("connection lost"))),
            );
          })),
      });

      return yield* stream.pipe(Stream.take(3), Stream.runCollect);
    }));

    expect(attempts).toEqual([1, 2, 3]);
  });

  /**
   * The ending that a `retry` alone would miss, and the more ordinary of the two:
   * a server that closes the response rather than erroring.
   */
  it("reopens after the connection ends cleanly", async () => {
    const attempts = await Effect.runPromise(Effect.gen(function*() {
      const opened = yield* Ref.make(0);

      const stream = yield* holdOpen({
        backoff: instant,
        onReconnect: Effect.void,
        open: () =>
          Stream.unwrap(Effect.map(
            Ref.updateAndGet(opened, (n) => n + 1),
            (attempt) => Stream.make(attempt),
          )),
      });

      return yield* stream.pipe(Stream.take(3), Stream.runCollect);
    }));

    expect(attempts).toEqual([1, 2, 3]);
  });

  it("catches up on every reconnect but not on the first connection", async () => {
    const [caughtUp, received] = await Effect.runPromise(Effect.gen(function*() {
      const opened = yield* Ref.make(0);
      const reconnects = yield* Ref.make(0);

      const stream = yield* holdOpen({
        backoff: instant,
        onReconnect: Ref.update(reconnects, (n) => n + 1),
        open: () =>
          Stream.unwrap(Effect.gen(function*() {
            const attempt = yield* Ref.updateAndGet(opened, (n) => n + 1);

            return Stream.make(attempt).pipe(
              Stream.concat(Stream.fail(new Error("connection lost"))),
            );
          })),
      });

      const values = yield* stream.pipe(Stream.take(3), Stream.runCollect);

      return [yield* Ref.get(reconnects), values] as const;
    }));

    // Three connections, two of them reconnections. The first is not one:
    // nothing has been missed yet and the queries are already loading.
    expect(received.length).toBe(3);
    expect(caughtUp).toBe(2);
  });

  it("does not catch up when the connection never drops", async () => {
    const caughtUp = await Effect.runPromise(Effect.gen(function*() {
      const reconnects = yield* Ref.make(0);

      const stream = yield* holdOpen({
        backoff: instant,
        onReconnect: Ref.update(reconnects, (n) => n + 1),
        open: () => Stream.make(1, 2, 3),
      });

      yield* stream.pipe(Stream.take(3), Stream.runCollect);

      return yield* Ref.get(reconnects);
    }));

    expect(caughtUp).toBe(0);
  });
});
