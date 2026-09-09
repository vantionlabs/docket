import { CommandPalette } from "@/components/app/command-palette.js";
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

/**
 * A router is needed for `useNavigate`. The contacts group is absent here because
 * its atom cannot reach `/rpc` in jsdom, which is the point of the `isSuccess`
 * guard around it — what is asserted below is the part that must work with no
 * data at all: the keybinding, and every page the sidebar offers.
 */
const renderPalette = async () => {
  const root = createRootRoute({ component: () => <CommandPalette /> });
  const router = createRouter({
    routeTree: root,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });

  await router.load();

  return render(<RouterProvider router={router as never} />);
};

const dialog = () => screen.queryByRole("dialog");

describe("CommandPalette", () => {
  it("stays shut until asked for", async () => {
    await renderPalette();

    expect(dialog()).not.toBeInTheDocument();
  });

  it("opens on the meta chord and closes on the same one", async () => {
    await renderPalette();

    await userEvent.keyboard("{Meta>}k{/Meta}");
    expect(dialog()).toBeInTheDocument();

    await userEvent.keyboard("{Meta>}k{/Meta}");
    expect(dialog()).not.toBeInTheDocument();
  });

  /** Ctrl as well as Cmd, so the shortcut is not macOS-only. */
  it("opens on the control chord too", async () => {
    await renderPalette();

    await userEvent.keyboard("{Control>}k{/Control}");

    expect(dialog()).toBeInTheDocument();
  });

  /**
   * These come from the arrays the sidebar and settings nav render from, so this
   * failing means the palette and the navigation have drifted apart.
   */
  it("offers every page the navigation does", async () => {
    await renderPalette();

    await userEvent.keyboard("{Meta>}k{/Meta}");

    for (const page of ["Dashboard", "Contacts", "Settings"]) {
      expect(screen.getByRole("option", { name: page })).toBeInTheDocument();
    }

    for (const page of ["General", "Members", "Roles", "API keys", "Audit log"]) {
      expect(screen.getByRole("option", { name: page })).toBeInTheDocument();
    }
  });

  it("filters to what was typed", async () => {
    await renderPalette();

    await userEvent.keyboard("{Meta>}k{/Meta}");
    await userEvent.type(screen.getByRole("combobox"), "audit");

    expect(screen.getByRole("option", { name: "Audit log" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Dashboard" })).not.toBeInTheDocument();
  });
});
