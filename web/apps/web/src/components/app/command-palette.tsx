import { contactsAtom } from "@/atom/contact-atoms.js";
import { nav } from "@/components/app/sidebar.js";
import { settingsGroups } from "@/components/settings/settings-nav.js";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command.js";
import { useAtomValue } from "@effect/atom-react";
import type { LinkProps } from "@tanstack/react-router";
import { useNavigate } from "@tanstack/react-router";
import { AsyncResult } from "effect/unstable/reactivity";
import * as React from "react";

/**
 * ⌘K, over destinations and records.
 *
 * The two "go to" groups are built from the arrays that already drive the sidebar
 * and the settings nav, exported for exactly this reason — a hand-typed second
 * list is how a page ends up reachable from one and not the other.
 *
 * On `RULES.md`'s rule that navigation must use real links: a `CommandItem` is not
 * an anchor, so these call `navigate`. That is acceptable here because the palette
 * is a keyboard accelerator over destinations which all remain real `<Link>`s in
 * the sidebar — it is not the only route to any of them.
 *
 * Mounted inside the signed-in shell, not the root: a palette listing an
 * organization's contacts on the sign-in page would be a bug, not a feature.
 */
export const CommandPalette = () => {
  const [open, setOpen] = React.useState(false);
  const navigate = useNavigate();

  const contacts = useAtomValue(contactsAtom);

  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // Ctrl as well as Cmd, so it works away from macOS.
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
      }
    };

    globalThis.addEventListener("keydown", onKeyDown);

    return () => {
      globalThis.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const go = (to: NonNullable<LinkProps["to"]>) => {
    setOpen(false);
    void navigate({ to });
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      {
        /* Base UI's CommandDialog is only the dialog — unlike the Radix one it
          does not wrap its children in a Command root, so cmdk's context has to
          be supplied here or every child throws. */
      }
      <Command>
        <CommandInput placeholder="Search contacts and pages…" />
        <CommandList>
          <CommandEmpty>Nothing matches that.</CommandEmpty>

          <CommandGroup heading="Go to">
            {nav.map(({ icon: Icon, label, to }) => (
              <CommandItem
                key={to}
                value={`go ${label}`}
                onSelect={() => {
                  go(to);
                }}
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </CommandItem>
            ))}
          </CommandGroup>

          <CommandGroup heading="Settings">
            {settingsGroups.flatMap((group) =>
              group.items.map(({ icon: Icon, label, to }) => (
                <CommandItem
                  key={to}
                  value={`settings ${group.label} ${label}`}
                  onSelect={() => {
                    go(to);
                  }}
                >
                  <Icon className="size-4" aria-hidden />
                  {label}
                </CommandItem>
              ))
            )}
          </CommandGroup>

          {AsyncResult.isSuccess(contacts) && contacts.value.length > 0 && (
            <CommandGroup heading="Contacts">
              {contacts.value.map((contact) => (
                <CommandItem
                  key={contact.id}
                  // Name and email both match, because which one somebody
                  // remembers about a contact is not predictable.
                  value={`contact ${contact.fullName} ${contact.email}`}
                  onSelect={() => {
                    go("/contacts");
                  }}
                >
                  {contact.fullName}
                  <span className="text-muted-foreground ml-auto text-xs">{contact.email}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  );
};
