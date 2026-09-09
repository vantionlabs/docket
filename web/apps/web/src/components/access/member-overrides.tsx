import { clearOverrideAtom, memberOverridesAtom, setOverrideAtom } from "@/atom/access-atoms.js";
import { PermissionPicker } from "@/components/access/permission-picker.js";
import { Badge } from "@/components/ui/badge.js";
import { Button } from "@/components/ui/button.js";
import { useAtomSet, useAtomValue } from "@effect/atom-react";
import { MemberOverride } from "@forge/domain/iam/AccessRpc";
import type { Permission } from "@forge/domain/iam/Permission";
import { permissionsFor } from "@forge/domain/iam/Permission";
import { AsyncResult } from "effect/unstable/reactivity";

/**
 * Overrides sit *on top of* the role, so this shows what the role already gives
 * and what has been added or taken away — a checkbox alone would hide which of
 * the two a permission came from.
 */
export const MemberOverrides = (props: {
  readonly memberId: string;
  readonly role: string;
}) => {
  const overrides = useAtomValue(memberOverridesAtom(props.memberId));
  const set = useAtomSet(setOverrideAtom);
  const clear = useAtomSet(clearOverrideAtom);

  if (!AsyncResult.isSuccess(overrides)) {
    return <p className="text-muted-foreground text-sm">loading overrides…</p>;
  }

  const fromRole = permissionsFor(props.role);
  const granted = new Set(
    overrides.value.filter((override) => override.granted).map((o) => o.permission),
  );
  const revoked = new Set(
    overrides.value.filter((override) => !override.granted).map((o) => o.permission),
  );

  const effective = new Set([...fromRole, ...granted]);
  for (const permission of revoked) effective.delete(permission);

  const toggle = (permission: Permission, checked: boolean) => {
    const inRole = fromRole.has(permission);

    // Match the role again and the override is redundant, so remove it rather
    // than storing a grant that says what the role already said.
    if (checked === inRole) clear({ memberId: props.memberId, permission });
    else set(new MemberOverride({ memberId: props.memberId, permission, granted: checked }));
  };

  return (
    <div className="flex flex-col gap-4 rounded-md border border-border p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">Overrides:</span>
        {granted.size === 0 && revoked.size === 0
          ? <span className="text-muted-foreground">none — permissions come from the role</span>
          : (
            <>
              {[...granted].map((permission) => (
                <Badge key={permission} className="font-mono text-xs">+{permission}</Badge>
              ))}
              {[...revoked].map((permission) => (
                <Badge key={permission} variant="destructive" className="font-mono text-xs">
                  −{permission}
                </Badge>
              ))}
            </>
          )}
      </div>

      <PermissionPicker selected={effective} onToggle={toggle} />

      {(granted.size > 0 || revoked.size > 0) && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => {
            for (const permission of [...granted, ...revoked]) {
              clear({ memberId: props.memberId, permission });
            }
          }}
        >
          Reset to role
        </Button>
      )}
    </div>
  );
};
