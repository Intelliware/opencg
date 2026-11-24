import { Badge } from "@/components/ui/badge";
import { type CostSummary, formatUsd } from "@/lib/cost";
import { cn } from "@/lib/utils";

/** Amber "unpriced" marker: usage with no price entry is never shown as free. */
export function UnpricedBadge({ className }: { className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "border-amber-500/60 px-1.5 py-0 font-medium text-amber-700 dark:text-amber-400",
        className,
      )}
    >
      unpriced
    </Badge>
  );
}

export interface CostValueProps {
  summary: CostSummary;
  /** Hide the "excludes unpriced usage" note (keeps the badge) for tight rows. */
  compact?: boolean;
  className?: string;
}

/** An estimated cost: "$0.000123", "$0.00", "—", or a priced subtotal marked unpriced. */
export function CostValue({ summary, compact = false, className }: CostValueProps) {
  if (summary.kind === "missing") {
    return (
      <span
        className={cn("text-muted-foreground", className)}
        title="Cost was not recorded for this request"
        data-testid="cost-value"
      >
        —
      </span>
    );
  }
  return (
    <span
      className={cn("inline-flex flex-wrap items-center gap-1 font-mono", className)}
      title={summary.kind === "partial" ? "Excludes unpriced usage" : "Estimated cost (USD)"}
      data-testid="cost-value"
    >
      <span>{formatUsd(summary.total)}</span>
      {summary.kind === "partial" && (
        <>
          <UnpricedBadge />
          {!compact && (
            <span className="font-sans text-xs text-muted-foreground">excludes unpriced usage</span>
          )}
        </>
      )}
    </span>
  );
}
