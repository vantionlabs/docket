import { Badge } from "@/components/ui/badge";
import type { DecisionStatus, Outcome } from "@/hooks/use-decisions";

type Variant = React.ComponentProps<typeof Badge>["variant"];

/**
 * One vocabulary for outcomes, used by the queue, the detail screen and the
 * audit log. A reviewer scanning forty rows learns the colours once.
 */
const OUTCOME: Record<Outcome, { label: string; variant: Variant }> = {
  auto_approve: { label: "Auto approve", variant: "success" },
  route_for_approval: { label: "Needs approval", variant: "warning" },
  reject: { label: "Reject", variant: "destructive" },
  needs_human: { label: "Needs a human", variant: "secondary" },
};

const STATUS: Record<DecisionStatus, { label: string; variant: Variant }> = {
  pending_review: { label: "In queue", variant: "warning" },
  approved: { label: "Approved", variant: "success" },
  rejected: { label: "Rejected", variant: "destructive" },
  executed: { label: "Executed", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
};

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  const { label, variant } = OUTCOME[outcome];
  return <Badge variant={variant}>{label}</Badge>;
}

export function StatusBadge({ status }: { status: DecisionStatus }) {
  const { label, variant } = STATUS[status];
  return <Badge variant={variant}>{label}</Badge>;
}

export { OUTCOME, STATUS };
