/**
 * Invalidation keys shared by every atom module.
 *
 * Each module builds its own `Atom.runtime`, but all of them come from the same
 * default factory, and that factory memoises a single `Reactivity` service per
 * registry — so a key invalidated by a mutation in one module refreshes the
 * queries registered in another. Reads subscribe with `Atom.withReactivity`,
 * writes announce with `reactivityKeys`.
 */
export const Keys = {
  /**
   * Everything the active organization scopes. Switching or creating one
   * invalidates it, and every org-scoped query subscribes to it — which is why
   * changing organization no longer needs a page reload.
   */
  organization: "organization",
  contacts: "contacts",
  /** The audit trail. Every mutation adds to it, so it is refreshed broadly. */
  audit: "audit",
  apiKeys: "apiKeys",
  roles: "roles",
  members: "members",
  overrides: "overrides",
} as const;
