import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen.js";

/**
 * A factory, not a module-level singleton.
 *
 * Start calls this once per request on the server, so two requests cannot share
 * a router — and with it, one visitor's matched data. The browser calls it once.
 */
export function getRouter() {
  return createRouter({ routeTree, scrollRestoration: true });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof getRouter>;
  }

  /**
   * The breadcrumb label for a route, declared on the route itself and read back
   * with `useMatches`.
   *
   * Declared rather than derived from the path: `knowledge/rules/dashboard-ui.md`
   * forbids humanising identifiers, so title-casing a slug would break the rules
   * by construction.
   *
   * Optional on purpose. `router-core` makes `staticData` a required route option
   * as soon as this interface has a required field, which would mean touching
   * every route and breaking the generated tree.
   */
  interface StaticDataRouteOption {
    readonly crumb?: string;
  }
}
