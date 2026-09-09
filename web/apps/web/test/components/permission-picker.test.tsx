import { PermissionPicker } from "@/components/access/permission-picker.js";
import { statements } from "@forge/domain/iam/Permission";
import type { Permission } from "@forge/domain/iam/Permission";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const allPermissions = Object.entries(statements).flatMap(([resource, actions]) =>
  actions.map((action) => `${resource}:${action}`)
);

describe("PermissionPicker", () => {
  it("renders every declared permission, grouped by resource", () => {
    render(<PermissionPicker selected={new Set()} onToggle={vi.fn()} />);

    for (const resource of Object.keys(statements)) {
      expect(screen.getByText(resource)).toBeInTheDocument();
    }

    // The picker is driven by the domain declaration, so adding a permission
    // there must surface here without touching this component.
    expect(screen.getAllByRole("checkbox")).toHaveLength(allPermissions.length);
  });

  it("checks exactly the permissions it was given", () => {
    render(
      <PermissionPicker
        selected={new Set<Permission>(["contact:read"])}
        onToggle={vi.fn()}
      />,
    );

    // Queried by accessible state rather than by a data attribute: Radix spelled
    // it `data-state="checked"` and Base UI spells it `data-checked`, and neither
    // is the thing under test.
    expect(screen.getAllByRole("checkbox", { checked: true })).toHaveLength(1);
  });

  it("reports the permission and its new state when toggled", async () => {
    const onToggle = vi.fn();
    render(<PermissionPicker selected={new Set()} onToggle={onToggle} />);

    // `organization` is declared first, and `update` is its first action.
    await userEvent.click(screen.getAllByRole("checkbox")[0]!);

    expect(onToggle).toHaveBeenCalledWith("organization:update", true);
  });

  it("does not fire while disabled", async () => {
    const onToggle = vi.fn();
    render(<PermissionPicker selected={new Set()} onToggle={onToggle} disabled />);

    await userEvent.click(screen.getAllByRole("checkbox")[0]!);

    expect(onToggle).not.toHaveBeenCalled();
  });
});
