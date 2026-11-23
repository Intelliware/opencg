import { PermissionDenied } from "@/components/PermissionDenied";

// Rendered by forbidden() when the pipeline answers 403 to a page's read.
export default function Forbidden() {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold tracking-tight">Access denied</h1>
      <PermissionDenied action="view this page" />
    </div>
  );
}
