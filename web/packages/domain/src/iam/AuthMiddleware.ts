import { RpcMiddleware } from "effect/unstable/rpc";
import { CurrentUser, Unauthenticated } from "./Identity.js";

/**
 * Applied to every authenticated RPC group. Resolves the session from request
 * headers and provides `CurrentUser` to the handlers beneath it.
 */
export class AuthMiddleware extends RpcMiddleware.Service<AuthMiddleware, {
  provides: CurrentUser;
}>()("AuthMiddleware", {
  error: Unauthenticated,
}) {}
