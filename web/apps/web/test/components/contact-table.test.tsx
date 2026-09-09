import { ContactTable } from "@/components/contact/contact-table.js";
import { Contact, ContactId } from "@forge/domain/contact/ContactRpc";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const contact = new Contact({
  id: ContactId.make("contact_1"),
  email: "contact@example.com",
  fullName: "A Contact",
});

describe("ContactTable", () => {
  it("shows an empty state rather than a bare table", () => {
    render(<ContactTable contacts={[]} onDelete={vi.fn()} />);

    expect(screen.getByText(/no contacts yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders a row per contact", () => {
    render(<ContactTable contacts={[contact]} onDelete={vi.fn()} />);

    expect(screen.getByText("A Contact")).toBeInTheDocument();
    expect(screen.getByText("contact@example.com")).toBeInTheDocument();
  });

  it("deletes by id, not by row position", async () => {
    const onDelete = vi.fn();
    render(<ContactTable contacts={[contact]} onDelete={onDelete} />);

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(onDelete).toHaveBeenCalledWith("contact_1");
  });
});
