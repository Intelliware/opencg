// Display rules for estimated model cost (add-observability-stack D10).
//
// - A dollar figure to 4 significant digits: $0.000123, $1.234, $1,235.00.
// - A cost priced at zero shows as $0.00.
// - "unpriced" when any provider in the row has no price; the total then
//   covers only the priced usage and says so.
// - "—" when the row carries no cost at all (written before cost was recorded).
import type { ProviderUsage } from "@opencg/shared";

export type CostSummary =
  | { kind: "missing" }
  | { kind: "priced"; total: number }
  | { kind: "partial"; total: number };

const SIG4 = new Intl.NumberFormat("en-US", {
  maximumSignificantDigits: 4,
  useGrouping: true,
});

/** Format a USD amount; null/undefined (not recorded) renders as "—". */
export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value === 0) return "$0.00";
  const sign = value < 0 ? "-" : "";
  let digits = SIG4.format(Math.abs(value));
  const dot = digits.indexOf(".");
  if (dot === -1) digits += ".00";
  else if (digits.length - dot - 1 === 1) digits += "0";
  return `${sign}$${digits}`;
}

/**
 * Summarise a row's cost from its total and per-provider usage.
 *
 * `providers` empty/absent and `total` null/absent means the row predates cost
 * recording. Any provider with `cost_usd: null`, or `complete === false`,
 * makes the summary partial; its total is then the priced subtotal.
 */
export function summarizeCost(
  total: number | null | undefined,
  providers?: readonly ProviderUsage[] | null,
  complete?: boolean,
): CostSummary {
  const list = providers ?? [];
  if ((total === null || total === undefined) && list.length === 0) return { kind: "missing" };
  const value = total ?? list.reduce((acc, p) => acc + (p.cost_usd ?? 0), 0);
  const unpriced = complete === false || list.some((p) => p.cost_usd === null);
  return unpriced ? { kind: "partial", total: value } : { kind: "priced", total: value };
}
