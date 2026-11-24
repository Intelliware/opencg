import type { ProviderUsage } from "@opencg/shared";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatUsd, summarizeCost } from "@/lib/cost";
import { CostValue, UnpricedBadge } from "./CostValue";

export interface CostBreakdownProps {
  /** Per (provider, model) usage. null/absent on rows written before cost was recorded. */
  providers?: readonly ProviderUsage[] | null;
  /** Sum of the priced entries; null/absent on older rows. */
  total?: number | null;
  /** False when the envelope reports an unpriced entry. */
  complete?: boolean;
}

/** Estimated cost by provider and model, with the request total. */
export function CostBreakdown({ providers, total, complete }: CostBreakdownProps) {
  const summary = summarizeCost(total, providers, complete);
  const rows = providers ?? [];

  if (rows.length === 0) {
    return (
      <div className="flex items-baseline gap-2 text-sm" data-testid="cost-breakdown">
        <span className="text-xs text-muted-foreground">Estimated cost</span>
        <CostValue summary={summary} />
        {summary.kind === "missing" && (
          <span className="text-xs text-muted-foreground">
            not recorded for this request
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-md border" data-testid="cost-breakdown">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Provider</TableHead>
            <TableHead>Model</TableHead>
            <TableHead className="text-right">Tokens in</TableHead>
            <TableHead className="text-right">Tokens out</TableHead>
            <TableHead className="text-right">Cost (USD)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((p) => (
            <TableRow key={`${p.provider}/${p.model}`}>
              <TableCell className="font-mono">{p.provider}</TableCell>
              <TableCell className="font-mono">{p.model}</TableCell>
              <TableCell className="text-right tabular-nums">{p.tokens_in}</TableCell>
              <TableCell className="text-right tabular-nums">{p.tokens_out}</TableCell>
              <TableCell className="text-right font-mono">
                {p.cost_usd === null ? <UnpricedBadge /> : formatUsd(p.cost_usd)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell colSpan={4}>Estimated total</TableCell>
            <TableCell className="text-right" data-testid="cost-total">
              <CostValue summary={summary} className="justify-end" />
            </TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  );
}
