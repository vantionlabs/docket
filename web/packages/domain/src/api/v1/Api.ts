import { Schema } from "effect";
import { HttpApi, HttpApiEndpoint, HttpApiGroup, HttpApiSchema } from "effect/unstable/httpapi";
import { ContactV1, Forbidden, NewContactV1, NotFound, Unauthorized } from "./Wire.js";

/**
 * Version 1 of the public HTTP API.
 *
 * ## Why this exists separately from the RPC group
 *
 * The RPC group is our own client's transport: ndjson, one path, tag-dispatched.
 * A fine internal contract and a poor public one — nobody integrates against a
 * bespoke envelope, and publishing it would freeze our internal wire format
 * forever. So the handlers are shared, through `ContactStore`, and the transport
 * is not.
 *
 * ## How versioning works
 *
 * The version is in the path, applied by `prefix` at the bottom. Path-based
 * because it is the one scheme that survives contact with `curl`, a browser
 * address bar and a customer's HTTP library — a version carried in a custom
 * `Accept` header is invisible in every log and every bug report.
 *
 * A v2 is a *sibling directory*, not an edit to this one. It gets its own frozen
 * `Wire` schemas and its own mapping from the domain, and this file keeps
 * compiling and serving unchanged. That is the point: adding v2 must not be able
 * to alter v1, and the only real guarantee of that is sharing no types.
 */

/** Every endpoint can fail these ways, so they are declared once. */
const authErrors = [
  // 401, not 403: a missing or wrong key is a failure to authenticate.
  Unauthorized.pipe(HttpApiSchema.status(401)),
  Forbidden.pipe(HttpApiSchema.status(403)),
] as const;

const contacts = HttpApiGroup.make("contacts")
  .add(HttpApiEndpoint.get("list", "/contacts", {
    success: Schema.Array(ContactV1),
    error: authErrors,
  }))
  .add(HttpApiEndpoint.post("create", "/contacts", {
    payload: NewContactV1,
    success: ContactV1.pipe(HttpApiSchema.status(201)),
    error: authErrors,
  }))
  .add(HttpApiEndpoint.delete("remove", "/contacts/:contactId", {
    params: { contactId: Schema.String },
    success: Schema.Void.pipe(HttpApiSchema.status(204)),
    error: [...authErrors, NotFound.pipe(HttpApiSchema.status(404))],
  }));

export const ApiV1 = HttpApi.make("forge-v1").add(contacts).prefix("/api/v1");
