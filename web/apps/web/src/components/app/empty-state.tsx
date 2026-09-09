import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty.js";
import type { LucideIcon } from "lucide-react";

/**
 * One empty state, used everywhere something can be empty.
 *
 * This existed thirteen times before, hand-rolled, in two different shapes — a
 * dashed box on the tables somebody remembered, and a bare sentence on the ones
 * they did not. A shared component is the only way a nineteenth list gets the
 * same treatment as the first.
 *
 * The icon is the same glyph the navigation uses for the thing that is missing,
 * which is what makes it informational rather than ornamental: an empty page says
 * *what* is empty before it is read. Per `knowledge/rules/dashboard-ui.md`, that
 * is the extent of it — no illustrations.
 *
 * `border` is set explicitly because the shadcn primitive ships `border-dashed`
 * with no width, and Tailwind's reset zeroes border width, so the dashes would
 * not render at all.
 */
export const EmptyState = (props: {
  readonly icon: LucideIcon;
  readonly title: string;
  readonly description: string;
  /** A way out of the empty state, when there is a single obvious one. */
  readonly action?: React.ReactNode;
}) => {
  const { icon: Icon } = props;

  return (
    <Empty className="border border-dashed border-border p-8 md:p-10">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Icon aria-hidden />
        </EmptyMedia>
        <EmptyTitle className="text-sm font-medium">{props.title}</EmptyTitle>
        <EmptyDescription className="text-sm">{props.description}</EmptyDescription>
      </EmptyHeader>
      {props.action !== undefined && <EmptyContent>{props.action}</EmptyContent>}
    </Empty>
  );
};
