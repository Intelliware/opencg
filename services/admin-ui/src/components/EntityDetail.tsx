import Link from "next/link";
import type { Entity } from "@opencg/shared";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const BODY_PREVIEW_CHARS = 50_000;

// SSR formats dates in the server's time zone but this component hydrates in the
// browser's, so date-bearing elements suppress the text mismatch (React #418).
function Pair({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div
        className={cn(
          "break-all text-sm",
          typeof value === "string" && value.length > 20 && "font-mono",
        )}
        suppressHydrationWarning
      >
        {value}
      </div>
    </div>
  );
}

export interface EntityDetailProps {
  entity: Entity;
  showFullBody?: boolean;
  onToggleFullBody?: () => void;
  onTombstone?: () => void;
}

export function EntityDetail({
  entity,
  showFullBody = false,
  onToggleFullBody,
  onTombstone,
}: EntityDetailProps) {
  const tombstoned = entity.tombstoned_at != null;
  const bodyTooLong = entity.body.length > BODY_PREVIEW_CHARS;
  const bodyShown = showFullBody ? entity.body : entity.body.slice(0, BODY_PREVIEW_CHARS);

  return (
    <article className="flex flex-col gap-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <h2 className="m-0 font-mono text-xl font-semibold">
          {entity.title ?? entity.source_uri}
        </h2>
        {tombstoned ? (
          <Badge variant="destructive" suppressHydrationWarning>
            Tombstoned at {new Date(entity.tombstoned_at as string).toLocaleString()}
          </Badge>
        ) : null}
      </header>

      <Card>
        <CardContent className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
          <Pair label="entity_id" value={entity.entity_id} />
          <Pair label="source" value={entity.source} />
          <Pair label="source_uri" value={entity.source_uri} />
          <Pair label="classification" value={entity.classification} />
          <Pair label="freshness_state" value={entity.freshness_state} />
          <Pair label="content_hash" value={entity.content_hash.slice(0, 16) + "…"} />
          <Pair
            label="last_verified_at"
            value={new Date(entity.last_verified_at).toLocaleString()}
          />
          <Pair
            label="ingested_at"
            value={new Date(entity.ingested_at).toLocaleString()}
          />
          <Pair
            label="updated_at"
            value={new Date(entity.updated_at).toLocaleString()}
          />
        </CardContent>
      </Card>

      <section>
        <h3 className="mb-2 mt-0 text-base font-semibold">Lineage</h3>
        <Card>
          <CardContent className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
            <div>
              <div className="mb-1 text-xs text-muted-foreground">Parent</div>
              {entity.lineage.parent ? (
                <Link
                  href={`/entities/${entity.lineage.parent.entity_id}`}
                  className="font-mono text-sm text-primary underline-offset-4 hover:underline"
                >
                  {entity.lineage.parent.title ?? entity.lineage.parent.source_uri}
                </Link>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </div>
            <div>
              <div className="mb-1 text-xs text-muted-foreground">
                Children ({entity.lineage.children.length})
              </div>
              {entity.lineage.children.length === 0 ? (
                <span className="text-muted-foreground">—</span>
              ) : (
                <ul className="m-0 max-h-[200px] list-disc overflow-auto pl-5">
                  {entity.lineage.children.map((c) => (
                    <li key={c.entity_id} className="font-mono text-xs">
                      <Link
                        href={`/entities/${c.entity_id}`}
                        className="text-primary underline-offset-4 hover:underline"
                      >
                        {c.title ?? c.source_uri}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CardContent>
        </Card>
      </section>

      <section>
        <header className="flex items-baseline justify-between">
          <h3 className="m-0 text-base font-semibold">Body</h3>
          {bodyTooLong ? (
            <Button type="button" variant="outline" size="sm" onClick={onToggleFullBody}>
              {showFullBody ? "Collapse" : `Show full body (${entity.body.length} chars)`}
            </Button>
          ) : null}
        </header>
        <pre className="mt-2 max-h-[400px] overflow-auto whitespace-pre-wrap break-words rounded-md border bg-muted p-3 text-sm">
          {bodyShown}
          {!showFullBody && bodyTooLong ? "\n\n… (truncated)" : ""}
        </pre>
      </section>

      <section>
        <h3 className="mb-2 mt-0 text-base font-semibold">Metadata</h3>
        <pre className="m-0 max-h-[200px] overflow-auto rounded-md border bg-muted p-3 text-xs">
          {JSON.stringify(entity.metadata, null, 2)}
        </pre>
      </section>

      <section>
        <h3 className="mb-2 mt-0 text-base font-semibold">
          Recent audit appearances ({entity.audit_appearances.length})
        </h3>
        {entity.audit_appearances.length === 0 ? (
          <p className="m-0 text-sm text-muted-foreground">
            This entity has not appeared in recently assembled context.
          </p>
        ) : (
          <ul className="m-0 list-disc pl-5">
            {entity.audit_appearances.map((appearance) => (
              <li key={appearance.id} className="mb-1.5">
                <a
                  href={`/queries/${appearance.id}`}
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {appearance.query || appearance.tool}
                </a>{" "}
                <span className="text-xs text-muted-foreground" suppressHydrationWarning>
                  {new Date(appearance.created_at).toLocaleString()} ·{" "}
                  {appearance.outcome}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {!tombstoned && onTombstone ? (
        <Card className="border-destructive/50">
          <CardHeader className="p-4 pb-0">
            <CardTitle className="text-red-600 dark:text-red-400">
              Tombstone entity
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <p className="mt-1.5 text-sm text-muted-foreground">
              Soft-delete this entity. It will be excluded from future retrievals.
              This action is reversible only by re-ingesting the source.
            </p>
            <Button
              type="button"
              variant="destructive"
              className="mt-1.5"
              onClick={onTombstone}
            >
              Tombstone
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </article>
  );
}
