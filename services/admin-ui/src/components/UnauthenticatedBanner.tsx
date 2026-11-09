import { ShieldAlert } from "lucide-react";

// Shown on every page while OPENCG__ADMIN_UI__PASSWORD is unset.
export function UnauthenticatedBanner() {
  return (
    <div
      role="status"
      className="mb-4 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100"
    >
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <p>
        <strong>Unauthenticated mode — local use only.</strong> Anyone who can reach this
        page can delete content and start ingestion runs. Set{" "}
        <code className="font-mono">OPENCG__ADMIN_UI__PASSWORD</code> before exposing it.
      </p>
    </div>
  );
}
