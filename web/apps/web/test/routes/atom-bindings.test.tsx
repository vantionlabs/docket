import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

/**
 * Every page renders without a missing binding.
 *
 * This exists because of a real failure: `ReferenceError: onboardingAtom is not
 * defined`, thrown inside a page. Nothing caught it — `tsc` sees the import, the
 * production bundle resolves it, and no test rendered the page — so the first
 * report came from somebody clicking through to it.
 *
 * The pages are imported dynamically and mounted for real. A module whose imports
 * do not line up with its uses throws on evaluation or on first render, and either
 * way this fails. Data is not stubbed: the atoms cannot reach `/rpc` under jsdom,
 * so each page renders its loading or failure branch — which is enough, because
 * what is under test is that the module and its bindings hold together.
 */
const mount = async (load: () => Promise<{ readonly node: React.ReactNode; }>) => {
  const { node } = await load();
  const root = createRootRoute({ component: () => node });
  const router = createRouter({
    routeTree: root,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });

  await router.load();

  return render(<RouterProvider router={router as never} />);
};

describe("page modules", () => {
  /**
   * Every signed-in page, mounted for real. Adding a route here is cheap and is
   * the only thing that keeps this honest as pages are added.
   */
  const pages = [
    ["the dashboard", () => import("@/routes/_protected/index.js")],
    ["contacts", () => import("@/routes/_protected/contacts.js")],
    ["settings general", () => import("@/routes/_protected/settings/general.js")],
    ["settings members", () => import("@/routes/_protected/settings/members.js")],
    ["settings roles", () => import("@/routes/_protected/settings/roles.js")],
    ["settings api keys", () => import("@/routes/_protected/settings/api-keys.js")],
    ["the audit log", () => import("@/routes/_protected/settings/audit.js")],
  ] as const;

  for (const [name, load] of pages) {
    it(`renders ${name}`, async () => {
      const { container } = await mount(async () => {
        // The components are not exported — the route is — so the route's own
        // component is what gets mounted, exactly as the router would mount it.
        const module = await load();
        const Component = module.Route.options.component!;

        return { node: <Component /> };
      });

      // The shell resolves no session under jsdom, so it renders its checking
      // state. Reaching that at all means every module in the chain evaluated.
      expect(container).not.toBeEmptyDOMElement();
    });
  }
});
