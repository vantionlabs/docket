import { RoleTable } from "@/components/access/role-table.js";
import { RegistryProvider } from "@effect/atom-react";
import { CustomRole } from "@forge/domain/iam/AccessRpc";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const renderTable = (roles: ReadonlyArray<CustomRole>, onEdit = vi.fn()) => {
  render(
    <RegistryProvider>
      <RoleTable roles={roles} onEdit={onEdit} />
    </RegistryProvider>,
  );

  return onEdit;
};

describe("RoleTable", () => {
  it("explains that built-in roles still exist when there are none", () => {
    renderTable([]);

    expect(screen.getByText(/no custom roles yet/i)).toBeInTheDocument();
    expect(screen.getByText(/owner, admin and member/i)).toBeInTheDocument();
  });

  it("lists each role with its permissions", () => {
    renderTable([
      new CustomRole({ role: "editor", permissions: ["contact:read", "contact:update"] }),
    ]);

    expect(screen.getByText("editor")).toBeInTheDocument();
    expect(screen.getByText("contact:read")).toBeInTheDocument();
    expect(screen.getByText("contact:update")).toBeInTheDocument();
  });

  it("says so rather than showing nothing when a role grants no permissions", () => {
    renderTable([new CustomRole({ role: "observer", permissions: [] })]);

    expect(screen.getByText("none")).toBeInTheDocument();
  });

  it("passes the whole role to the edit handler, so the form can prefill", async () => {
    const role = new CustomRole({ role: "editor", permissions: ["contact:read"] });
    const onEdit = renderTable([role]);

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(onEdit).toHaveBeenCalledWith(role);
  });
});
