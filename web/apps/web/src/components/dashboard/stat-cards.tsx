import { overviewAtom } from "@/atom/contact-atoms.js";
import { StatCard } from "@/components/dashboard/stat-card.js";
import { Skeleton } from "@/components/ui/skeleton.js";
import { useAtomValue } from "@effect/atom-react";
import type { Overview } from "@forge/domain/contact/ContactRpc";
import { AsyncResult } from "effect/unstable/reactivity";

/**
 * Three numbers, three subscriptions.
 *
 * Each card selects the single field it renders, so it re-renders only when that
 * number changes. Reading the whole `Overview` in one component meant any write
 * that moved one count re-rendering every other card on the page alongside it.
 *
 * The selectors are module-level constants rather than inline arrows on purpose:
 * `useAtomValue` maps the atom before subscribing, so a fresh function per render
 * would build a fresh mapped atom per render and defeat the whole exercise.
 */
const count =
  (read: (overview: Overview) => number) => (result: AsyncResult.AsyncResult<Overview, unknown>) =>
    AsyncResult.isSuccess(result) ? read(result.value) : null;

const selectContacts = count((overview) => overview.contacts);
const selectMembers = count((overview) => overview.members);
const selectCustomRoles = count((overview) => overview.customRoles);

const Stat = (props: {
  readonly label: string;
  readonly select: (result: AsyncResult.AsyncResult<Overview, unknown>) => number | null;
}) => {
  const value = useAtomValue(overviewAtom, props.select);

  return value === null
    ? <Skeleton className="h-24 w-full" />
    : <StatCard label={props.label} value={value} />;
};

export const StatCards = () => (
  <div className="grid gap-4 sm:grid-cols-3">
    <Stat label="Contacts" select={selectContacts} />
    <Stat label="Members" select={selectMembers} />
    <Stat label="Custom roles" select={selectCustomRoles} />
  </div>
);
