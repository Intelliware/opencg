import { Lock } from "lucide-react";

import { permissionDeniedMessage } from "@/lib/auth/errors";
import { cn } from "@/lib/utils";

export interface PermissionDeniedProps {
  /** What the user tried to do, e.g. "tombstone this entity". */
  action: string;
  /** Optional extra line, e.g. which role is needed. */
  detail?: string;
  className?: string;
}

/** Shown when the pipeline answers 403: names the action, not an error page. */
export function PermissionDenied({ action, detail, className }: PermissionDeniedProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/5 px-3 py-2 text-sm text-red-700 dark:text-red-300",
        className,
      )}
    >
      <Lock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <p>
        <strong>{permissionDeniedMessage(action)}</strong>{" "}
        {detail ?? "Ask an openCG administrator for a role that allows it."}
      </p>
    </div>
  );
}
