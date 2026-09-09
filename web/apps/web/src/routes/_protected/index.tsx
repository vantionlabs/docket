import { StatCards } from "@/components/dashboard/stat-cards.js";
import { createFileRoute } from "@tanstack/react-router";

/**
 * The page reads no atom itself.
 *
 * Each section subscribes for itself, so a change to one does not re-render the
 * others. Reading everything here and passing it down is what makes a page
 * re-render wholesale on any write.
 */
const Dashboard = () => (
  <section className="flex flex-col gap-6">
    <div>
      <h1 className="text-lg font-semibold">Dashboard</h1>
      <p className="text-sm text-muted-foreground">Your organization at a glance</p>
    </div>

    <StatCards />
  </section>
);

export const Route = createFileRoute("/_protected/")({
  staticData: { crumb: "Dashboard" },
  component: Dashboard,
});
