import { IamRpcs } from "@forge/domain/iam/IamRpc";
import { CurrentUser } from "@forge/domain/iam/Identity";
import { permissionsFor } from "@forge/domain/iam/Permission";
import { Effect } from "effect";

/**
 * `CurrentUser` is a service key, and in v4 a service key *is* an
 * `Effect<Identity, never, CurrentUser>` — so the handler is the key itself,
 * with no conversion step.
 */
export const IamRpcLive = IamRpcs.toLayer(
  Effect.sync(() =>
    IamRpcs.of({
      Me: () => CurrentUser,

      MyPermissions: () =>
        Effect.map(CurrentUser, (identity) => Array.from(permissionsFor(identity.role))),
    })
  ),
);
