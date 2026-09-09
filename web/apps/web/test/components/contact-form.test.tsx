import { ContactForm } from "@/components/contact/contact-form.js";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

describe("ContactForm", () => {
  it("stays disabled until both fields have content", async () => {
    render(<ContactForm onCreate={vi.fn()} pending={false} />);
    const submit = screen.getByRole("button", { name: /add contact/i });

    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Name"), "A Contact");
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Email"), "contact@example.com");
    expect(submit).toBeEnabled();
  });

  it("trims input and clears the fields after submitting", async () => {
    const onCreate = vi.fn();
    render(<ContactForm onCreate={onCreate} pending={false} />);

    await userEvent.type(screen.getByLabelText("Name"), "  A Contact  ");
    await userEvent.type(screen.getByLabelText("Email"), "  contact@example.com  ");
    await userEvent.click(screen.getByRole("button", { name: /add contact/i }));

    expect(onCreate).toHaveBeenCalledWith({ email: "contact@example.com", fullName: "A Contact" });
    expect(screen.getByLabelText("Name")).toHaveValue("");
  });

  it("cannot be submitted twice while a create is in flight", () => {
    render(<ContactForm onCreate={vi.fn()} pending />);

    expect(screen.getByRole("button", { name: /add contact/i })).toBeDisabled();
  });
});
