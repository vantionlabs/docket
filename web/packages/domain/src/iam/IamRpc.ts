import { Schema } from "effect";
import { Rpc, RpcGroup } from "effect/unstable/rpc";
import { AuthMiddleware } from "./AuthMiddleware.js";
import { Identity } from "./Identity.js";
import { PermissionSchema } from "./Permission.js";

/**
 * Identity procedures. `AuthMiddleware` provides `CurrentUser` to every handler
 * in the group, so none of them take a caller or an org as a payload.
 */
export const IamRpcs = RpcGroup.make(
  Rpc.make("Me", { success: Identity }),
  /** What the caller may do, so a client can hide what it cannot use. */
  Rpc.make("MyPermissions", { success: Schema.Array(PermissionSchema) }),
).middleware(AuthMiddleware);
