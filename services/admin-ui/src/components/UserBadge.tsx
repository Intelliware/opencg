import { cn } from "@/lib/utils";

export interface UserBadgeProps {
  /** The signed-in principal (preferred_username, or sub). */
  principal: string;
  roles: string[];
  className?: string;
}

/** The signed-in user, shown in the sidebar footer in `oidc` mode. */
export function UserBadge({ principal, roles, className }: UserBadgeProps) {
  const roleText = roles.length > 0 ? roles.join(", ") : "no roles";
  return (
    <div className={cn("flex min-w-0 items-center gap-2", className)} aria-label={`Signed in as ${principal}`}>
      <span
        aria-hidden
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold uppercase text-foreground"
      >
        {principal.slice(0, 1) || "?"}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-xs font-medium text-foreground" title={principal}>
          {principal}
        </span>
        <span className="block truncate text-[11px] text-muted-foreground" title={roleText}>
          {roleText}
        </span>
      </span>
    </div>
  );
}
