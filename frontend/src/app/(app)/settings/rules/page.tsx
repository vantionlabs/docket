"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Rule = {
  id: string;
  name: string;
  schema_name: string;
  conditions: {
    max_total_incl_vat?: string;
    approved_suppliers?: string[];
    require_po?: boolean;
  };
  auto_approve: boolean;
  active: boolean;
  created_at: string;
};

const EMPTY = {
  name: "",
  max_total_incl_vat: "1000",
  approved_suppliers: "",
  require_po: true,
  auto_approve: false,
};

/**
 * Rules: the explicit gate of rail 3.
 *
 * The model proposes an outcome; a rule decides whether a human sees it.
 * Arming one is the only way anything executes without review, so the
 * screen says that in as many words rather than presenting a toggle that
 * looks like any other setting.
 */
export default function RulesPage() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["rules"],
    queryFn: () => api.get<Rule[]>("/rules"),
  });
  const rules = data ?? [];

  const invalidate = () => qc.invalidateQueries({ queryKey: ["rules"] });

  const create = useMutation({
    mutationFn: (body: unknown) => api.post<Rule>("/rules", body),
    onSuccess: () => {
      setDraft(EMPTY);
      void invalidate();
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/rules/${id}`),
    onSuccess: invalidate,
  });

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({
        name: draft.name,
        schema_name: "invoice",
        auto_approve: draft.auto_approve,
        active: true,
        conditions: {
          max_total_incl_vat: draft.max_total_incl_vat || "0",
          approved_suppliers: draft.approved_suppliers
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean),
          require_po: draft.require_po,
        },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the rule");
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-lg font-semibold tracking-tight">Rules</h1>
      <p className="text-muted-foreground mt-1 text-sm">
        A rule decides whether an outcome the pipeline proposed can execute
        without a person seeing it. Nothing auto-approves unless a rule here
        says so and every one of its conditions holds.
      </p>

      <ul className="mt-8 divide-y border-y">
        {isLoading && (
          <li className="text-muted-foreground py-6 text-sm">Loading…</li>
        )}
        {!isLoading && rules.length === 0 && (
          <li className="text-muted-foreground py-6 text-sm">
            No rules yet, so every decision goes to the queue. That is the
            right place to start.
          </li>
        )}
        {rules.map((rule) => (
          <li key={rule.id} className="group flex items-start gap-3 py-4">
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 text-sm font-medium">
                {rule.name}
                {rule.auto_approve ? (
                  <Badge variant="warning" className="gap-1">
                    <AlertTriangle size={10} /> executes without review
                  </Badge>
                ) : (
                  <Badge variant="secondary">queues everything</Badge>
                )}
                {!rule.active && <Badge variant="outline">inactive</Badge>}
              </p>
              <p className="text-muted-foreground mt-1 text-xs">
                Up to {rule.conditions.max_total_incl_vat ?? "0"} ·{" "}
                {rule.conditions.require_po
                  ? "PO required"
                  : "no PO required"}{" "}
                ·{" "}
                {rule.conditions.approved_suppliers?.length
                  ? `${rule.conditions.approved_suppliers.length} approved supplier(s)`
                  : "any supplier"}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Delete ${rule.name}`}
              onClick={() => void remove.mutateAsync(rule.id)}
              className="text-muted-foreground hover:text-destructive size-7"
            >
              <Trash2 size={14} />
            </Button>
          </li>
        ))}
      </ul>

      <form onSubmit={onCreate} className="mt-8 space-y-4">
        <h2 className="text-sm font-medium">New rule</h2>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              required
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="cost-centre-owner-limit"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="limit">Maximum total including VAT</Label>
            <Input
              id="limit"
              inputMode="decimal"
              value={draft.max_total_incl_vat}
              onChange={(e) =>
                setDraft({ ...draft, max_total_incl_vat: e.target.value })
              }
            />
            <p className="text-muted-foreground text-xs">
              Inclusive. Leave at 0 and the rule approves nothing.
            </p>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="suppliers">Approved suppliers</Label>
          <textarea
            id="suppliers"
            rows={3}
            value={draft.approved_suppliers}
            onChange={(e) =>
              setDraft({ ...draft, approved_suppliers: e.target.value })
            }
            placeholder={"One exact name per line\nContoso Cleaning Services BV"}
            className="border-input placeholder:text-muted-foreground focus-visible:ring-ring w-full rounded-md border bg-transparent px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none"
          />
          <p className="text-muted-foreground text-xs">
            Leave empty and the rule does not check the supplier.
          </p>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.require_po}
            onChange={(e) =>
              setDraft({ ...draft, require_po: e.target.checked })
            }
          />
          Require a purchase order number
        </label>

        <label className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={draft.auto_approve}
            onChange={(e) =>
              setDraft({ ...draft, auto_approve: e.target.checked })
            }
          />
          <span>
            <span className="font-medium text-amber-900">
              Let this rule execute without review
            </span>
            <span className="mt-0.5 block text-xs text-amber-800">
              Only turn this on once your eval set says the rule is safe. A
              decision it approves is paid without anybody seeing it.
            </span>
          </span>
        </label>

        {error && <p className="text-destructive text-sm">{error}</p>}

        <Button type="submit" disabled={create.isPending}>
          <Plus size={14} /> Create rule
        </Button>
      </form>
    </div>
  );
}
