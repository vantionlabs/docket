import { AppRpc } from "@/atom/app-rpc.js";
import { Effect } from "effect";

/**
 * Latest health report, refetched on demand via `useAtomRefresh`.
 */
export const healthAtom = AppRpc.runtime.atom(
  Effect.gen(function*() {
    const client = yield* AppRpc;

    return yield* client("Check", undefined);
  }),
);
