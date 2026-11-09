import { VectorExplorer } from "./VectorExplorer";
import { getReadyz } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function VectorsPage() {
  // Server-side fetch the readyz so we can show the active embedding model
  // info in the header before any client-side request fires.
  const readyz = await getReadyz();
  return (
    <section>
      <header className="mb-3 flex items-baseline gap-3">
        <h1 className="m-0">Vector search</h1>
        <span className="text-xs text-muted-foreground">
          tenant: {readyz?.tenant ?? "?"}
        </span>
        <span className="text-xs text-muted-foreground">
          model: <code>{readyz?.embedding_model ?? "unknown"}</code>
        </span>
        <span className="text-xs text-muted-foreground">
          dimensions: {readyz?.vector_size ?? "?"}
        </span>
      </header>
      <p className="mt-0 text-muted-foreground">
        Search the embedded catalogue. Every request reuses the pipeline&apos;s
        embeddings client; vector search is admin-only and does not write an
        audit row.
      </p>
      <VectorExplorer />
    </section>
  );
}
