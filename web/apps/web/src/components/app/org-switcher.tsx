import {
  createOrganizationAtom,
  organizationsAtom,
  switchOrganizationAtom,
} from "@/atom/organization-atoms.js";
import { Button } from "@/components/ui/button.js";
import { Input } from "@/components/ui/input.js";
import { useAtomSet, useAtomValue } from "@effect/atom-react";
import type { Membership } from "@forge/domain/iam/OrganizationRpc";
import { Exit } from "effect";
import { AsyncResult } from "effect/unstable/reactivity";
import * as React from "react";

const row = "w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent";

/**
 * Switching changes the session's active organization server-side.
 *
 * Both writes carry the `organization` invalidation key, so everything scoped
 * to an organization — the session, this list, contacts, the access tables —
 * re-reads itself once the write lands. Nothing here reloads the page or waits
 * out a guessed delay.
 */
export const OrgSwitcher = () => {
  const organizations = useAtomValue(organizationsAtom);
  const switchTo = useAtomSet(switchOrganizationAtom, { mode: "promiseExit" });
  const switching = useAtomValue(switchOrganizationAtom);
  const create = useAtomSet(createOrganizationAtom, { mode: "promiseExit" });
  const creating = useAtomValue(createOrganizationAtom);

  const [open, setOpen] = React.useState(false);
  const [naming, setNaming] = React.useState(false);
  const [name, setName] = React.useState("");

  if (!AsyncResult.isSuccess(organizations)) {
    return <p className="px-2 text-xs text-muted-foreground">loading…</p>;
  }

  const active = organizations.value.find((membership) => membership.isActive);

  const close = () => {
    setOpen(false);
    setNaming(false);
    setName("");
  };

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        className="flex w-full items-center justify-between rounded-md border border-border px-2 py-1.5 text-left text-sm hover:bg-accent"
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        <span className="truncate">{active?.name ?? "No organization"}</span>
        <span className="text-muted-foreground text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="flex flex-col gap-1 rounded-md border border-border p-1">
          {organizations.value.map((membership) => (
            <OrgRow
              key={membership.orgId}
              membership={membership}
              disabled={switching.waiting}
              onSelect={() => {
                if (membership.isActive) return close();

                // Held open until the switch lands, so a failure stays visible
                // rather than being hidden behind a closed menu.
                void switchTo(membership.orgId).then((exit) => {
                  if (Exit.isSuccess(exit)) close();
                });
              }}
            />
          ))}

          {naming
            ? (
              <div className="flex flex-col gap-1 p-1">
                <Input
                  autoFocus
                  value={name}
                  placeholder="Organization name"
                  onChange={(event) => setName(event.target.value)}
                />
                <Button
                  type="button"
                  size="sm"
                  disabled={name.trim() === "" || creating.waiting}
                  onClick={() =>
                    void create(name.trim()).then((exit) => {
                      if (Exit.isSuccess(exit)) close();
                    })}
                >
                  Create
                </Button>
              </div>
            )
            : (
              <button type="button" className={row} onClick={() => setNaming(true)}>
                + New organization
              </button>
            )}

          {(AsyncResult.isFailure(switching) || AsyncResult.isFailure(creating)) && (
            <p className="px-2 py-1 text-xs text-destructive">
              That did not work. Try again.
            </p>
          )}
        </div>
      )}
    </div>
  );
};

const OrgRow = (props: {
  readonly membership: Membership;
  readonly disabled: boolean;
  readonly onSelect: () => void;
}) => (
  <button type="button" className={row} disabled={props.disabled} onClick={props.onSelect}>
    <span className="flex items-center justify-between gap-2">
      <span className="truncate">{props.membership.name}</span>
      <span className="shrink-0 font-mono text-xs text-muted-foreground">
        {props.membership.isActive ? "active" : props.membership.role}
      </span>
    </span>
  </button>
);
