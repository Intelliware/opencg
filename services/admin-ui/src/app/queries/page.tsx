import { QueryRow } from "@/components/QueryRow";
import { listRecentAudits } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function QueriesPage() {
  const rows = await listRecentAudits(100);

  return (
    <section>
      <h1>Queries</h1>
      <p className="text-muted-foreground">
        Most recent {rows.length} audited retrievals from the pipeline. Click a row
        to see the full audit record and the assembled context.
      </p>

      {rows.length === 0 ? (
        <div className="rounded-md border border-dashed p-6 text-muted-foreground">
          No queries yet. Try ingesting a git repo with{" "}
          <code>make ingest-git REPO=…</code> and then call the MCP server.
        </div>
      ) : (
        <div className="mt-3 rounded-md border">
          {rows.map((r) => (
            <QueryRow
              key={r.id}
              id={r.id}
              created_at={r.created_at}
              principal={r.principal}
              tool={r.tool}
              query={r.query}
              tokens_in={r.tokens_in}
              tokens_out={r.tokens_out}
              latency_ms={r.latency_ms}
              outcome={r.outcome}
              estimated_cost_usd={r.estimated_cost_usd}
              usage_by_provider={r.usage_by_provider}
            />
          ))}
        </div>
      )}
    </section>
  );
}
