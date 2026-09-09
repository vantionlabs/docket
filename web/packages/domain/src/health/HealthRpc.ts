import { Rpc, RpcGroup } from "effect/unstable/rpc";
import { DatabaseUnreachable, HealthReport } from "./Health.js";

export const HealthRpcs = RpcGroup.make(
  Rpc.make("Ping"),
  Rpc.make("Check", {
    success: HealthReport,
    error: DatabaseUnreachable,
  }),
);
