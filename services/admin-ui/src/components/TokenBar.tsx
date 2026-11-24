import type { CostSummary } from "@/lib/cost";
import { CostValue } from "./CostValue";

export interface TokenBarProps {
  tokens_in: number;
  tokens_out: number;
  compact?: boolean;
  /** Optional estimated cost line under the bar (see `summarizeCost`). */
  cost?: CostSummary;
}

export function TokenBar({ tokens_in, tokens_out, compact = false, cost }: TokenBarProps) {
  const total = Math.max(1, tokens_in + tokens_out);
  const inPct = Math.round((tokens_in / total) * 100);
  const outPct = 100 - inPct;
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex flex-col gap-0.5" title={`in: ${tokens_in}, out: ${tokens_out}`}>
        {!compact && (
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>↑ {tokens_in}</span>
            <span>↓ {tokens_out}</span>
          </div>
        )}
        <div className={`flex overflow-hidden rounded bg-muted ${compact ? "h-1.5" : "h-2"}`}>
          <span className="bg-primary" style={{ width: `${inPct}%` }} />
          <span
            className="bg-emerald-600 dark:bg-emerald-400"
            style={{ width: `${outPct}%` }}
          />
        </div>
      </div>
      {cost && <CostValue summary={cost} compact={compact} className="text-xs" />}
    </div>
  );
}
