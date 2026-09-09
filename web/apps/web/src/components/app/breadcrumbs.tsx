import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb.js";
import type { LinkProps } from "@tanstack/react-router";
import { Link, useMatches } from "@tanstack/react-router";
import * as React from "react";

/**
 * Where you are, assembled from the matched routes' own `crumb` declarations.
 *
 * Matches without a crumb are skipped, so pathless layouts and redirect-only
 * index routes do not appear as gaps. Everything but the last crumb is a real
 * link.
 *
 * `select` narrows what this subscribes to, so a loader settling somewhere in the
 * tree does not re-render the trail.
 *
 * Crumbs are constants, deliberately. A detail page's crumb names its *kind*
 * ("Contact") rather than the record, because the record's name is already the
 * page heading directly below — and threading a value from a page up into the
 * shell that renders this would be real machinery for a duplicated word.
 */
export const Breadcrumbs = () => {
  const crumbs = useMatches({
    select: (matches) =>
      matches.flatMap((match) =>
        match.staticData.crumb === undefined ? [] : [{
          crumb: match.staticData.crumb,
          /**
           * `fullPath` spells an index route with a trailing slash — `/settings/`
           * — which is not one of the literals `Link` accepts, so it is trimmed.
           * The assertion is the cost of that: the trimmed value is a valid route
           * by construction, but `replace` widens the union to `string` and there
           * is no way to prove it back.
           */
          to: match.fullPath.replace(/(.)\/$/, "$1") as NonNullable<LinkProps["to"]>,
        }]
      ),
  });

  if (crumbs.length === 0) return null;

  return (
    <Breadcrumb>
      <BreadcrumbList>
        {crumbs.map((entry, index) => {
          const last = index === crumbs.length - 1;

          return (
            // The separator is itself an `<li>`, so it is a sibling of the item
            // rather than a child of it — nested inside, it is invalid HTML.
            <React.Fragment key={entry.to}>
              <BreadcrumbItem>
                {last
                  ? <BreadcrumbPage>{entry.crumb}</BreadcrumbPage>
                  : (
                    // Base UI takes a `render` element where Radix took
                    // `asChild`; the child is passed rather than wrapped.
                    <BreadcrumbLink render={<Link to={entry.to} />}>
                      {entry.crumb}
                    </BreadcrumbLink>
                  )}
              </BreadcrumbItem>
              {!last && <BreadcrumbSeparator />}
            </React.Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
};
