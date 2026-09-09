import { QueueTable } from "@/components/decision/queue-table.js";
import { DecisionId, DecisionSummary } from "@forge/domain/decision/DecisionRpc";
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DateTime } from "effect";
import { describe, expect, it, vi } from "vitest";

const decision = (id: string, outcome: string) =>
  new DecisionSummary({
    id: DecisionId.make(id),
    outcome,
    effectiveOutcome: outcome,
    status: "pending_review",
    assignedTo: null,
    groundingPassed: true,
    decidedAt: DateTime.makeUnsafe("2026-09-01T00:00:00Z"),
  });

const three = [
  decision("dec_1", "approve"),
  decision("dec_2", "route_to_cost_centre"),
  decision("dec_3", "escalate"),
];

/** The table renders a `Link`, so it needs a router around it. */
const mount = async (node: React.ReactNode) => {
  const router = createRouter({
    routeTree: createRootRoute({ component: () => node }),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });

  await router.load();

  return render(<RouterProvider router={router as never} />);
};

const props = {
  decisions: three,
  busy: false,
  onApprove: vi.fn(),
  onReject: vi.fn(),
  onOpen: vi.fn(),
};

describe("QueueTable", () => {
  it("shows an empty state rather than a bare table", async () => {
    await mount(<QueueTable {...props} decisions={[]} />);

    expect(screen.getByText(/nothing waiting/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("selects the first row, and j and k move the selection", async () => {
    const user = userEvent.setup();
    await mount(<QueueTable {...props} />);

    const rows = () => screen.getAllByRole("row").slice(1);
    expect(rows()[0]).toHaveAttribute("aria-selected", "true");

    await user.keyboard("j");
    expect(rows()[1]).toHaveAttribute("aria-selected", "true");

    await user.keyboard("k");
    expect(rows()[0]).toHaveAttribute("aria-selected", "true");
  });

  it("does not run off either end", async () => {
    const user = userEvent.setup();
    await mount(<QueueTable {...props} />);

    const rows = () => screen.getAllByRole("row").slice(1);

    await user.keyboard("kkk");
    expect(rows()[0]).toHaveAttribute("aria-selected", "true");

    await user.keyboard("jjjjj");
    expect(rows()[2]).toHaveAttribute("aria-selected", "true");
  });

  it("acts on the selected row rather than the first", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const user = userEvent.setup();
    await mount(<QueueTable {...props} onApprove={onApprove} onReject={onReject} />);

    await user.keyboard("j");
    await user.keyboard("a");
    expect(onApprove).toHaveBeenCalledWith("dec_2");

    await user.keyboard("j");
    await user.keyboard("r");
    expect(onReject).toHaveBeenCalledWith("dec_3");
  });

  it("opens the selected decision on Enter", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    await mount(<QueueTable {...props} onOpen={onOpen} />);

    await user.keyboard("{Enter}");
    expect(onOpen).toHaveBeenCalledWith("dec_1");
  });

  /**
   * The shortcuts are bound to the window, so anything typed into a field would
   * otherwise approve an invoice. `a` and `r` are ordinary letters -- somebody
   * writing a note is the likeliest way to hit this.
   */
  it("leaves keystrokes aimed at a field alone", async () => {
    const onApprove = vi.fn();
    const user = userEvent.setup();
    await mount(
      <>
        <textarea aria-label="note" />
        <QueueTable {...props} onApprove={onApprove} />
      </>,
    );

    await user.click(screen.getByLabelText("note"));
    await user.keyboard("arrange");

    expect(onApprove).not.toHaveBeenCalled();
    expect(screen.getByLabelText("note")).toHaveValue("arrange");
  });

  it("does nothing while a review is in flight", async () => {
    const onApprove = vi.fn();
    const user = userEvent.setup();
    await mount(<QueueTable {...props} busy onApprove={onApprove} />);

    await user.keyboard("a");
    expect(onApprove).not.toHaveBeenCalled();
  });
});
