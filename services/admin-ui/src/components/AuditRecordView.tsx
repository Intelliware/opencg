import type { ProviderUsage } from "@opencg/shared";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { CostBreakdown } from "./CostBreakdown";
import { TokenBar } from "./TokenBar";

export interface AuditRecordViewProps {
  record: {
    id: number;
    created_at: string;
    correlation_id: string;
    tenant: string;
    principal: string;
    roles: string[];
    tool: string;
    query: string;
    candidate_ids: string[];
    final_entity_ids: string[];
    final_context_hash: string;
    tokens_in: number;
    tokens_out: number;
    latency_ms: number;
    outcome: "ok" | "error";
    error_code?: string | null;
    /** Null/absent on rows written before cost was recorded. */
    estimated_cost_usd?: number | null;
    usage_by_provider?: readonly ProviderUsage[] | null;
  };
}

function Pair({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={cn(
          typeof value === "string" && value.length > 20 && "font-mono"
        )}
      >
        {value}
      </div>
    </div>
  );
}

export function AuditRecordView({ record }: AuditRecordViewProps) {
  return (
    <article className="flex flex-col gap-4">
      <header className="flex items-baseline gap-3">
        <h2 className="m-0">Audit #{record.id}</h2>
        <Badge
          variant={record.outcome === "ok" ? "secondary" : "destructive"}
          className={cn(
            record.outcome === "ok" &&
              "text-emerald-600 dark:text-emerald-400"
          )}
        >
          {record.outcome.toUpperCase()}
        </Badge>
      </header>

      <Card>
        <CardContent className="grid grid-cols-3 gap-3 p-3">
          <Pair label="created_at" value={new Date(record.created_at).toLocaleString()} />
          <Pair label="correlation_id" value={record.correlation_id} />
          <Pair label="tenant" value={record.tenant} />
          <Pair label="principal" value={record.principal} />
          <Pair label="roles" value={record.roles.join(", ")} />
          <Pair label="tool" value={record.tool} />
          <Pair label="latency_ms" value={`${record.latency_ms} ms`} />
          <Pair label="final_context_hash" value={record.final_context_hash.slice(0, 16) + "…"} />
          <Pair label="error_code" value={record.error_code ?? "—"} />
        </CardContent>
      </Card>

      <section>
        <div className="mb-1 text-xs text-muted-foreground">Query</div>
        <pre className="m-0 rounded-md bg-muted p-3 text-sm">{record.query}</pre>
      </section>

      <section>
        <div className="mb-1 text-xs text-muted-foreground">Token usage</div>
        <TokenBar tokens_in={record.tokens_in} tokens_out={record.tokens_out} />
      </section>

      <section>
        <div className="mb-1 text-xs text-muted-foreground">Estimated cost by provider</div>
        <CostBreakdown
          total={record.estimated_cost_usd}
          providers={record.usage_by_provider}
        />
      </section>

      <section>
        <div className="mb-1 text-xs text-muted-foreground">
          Candidates ({record.candidate_ids.length}) → final ({record.final_entity_ids.length})
        </div>
        <ul className="m-0 list-disc pl-5">
          {record.final_entity_ids.map((id) => (
            <li key={id} className="font-mono">
              {id}
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}
