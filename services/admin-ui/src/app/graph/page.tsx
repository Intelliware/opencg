import { CandidateEdgeRow } from "@/components/CandidateEdgeRow";
import { ConceptDetail } from "@/components/ConceptDetail";
import { ConceptRow } from "@/components/ConceptRow";
import { VocabRow } from "@/components/VocabRow";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { VocabCreateForm } from "./GraphActions";
import { GraphExplorer } from "./GraphExplorer";
import { getGraphConcept, listGraphConcepts, listGraphEdges, listGraphVocabulary } from "@/lib/api";

export const dynamic = "force-dynamic";

const TABS = [
  { value: "map", label: "Map" },
  { value: "concepts", label: "Concepts" },
  { value: "candidates", label: "Candidate review" },
  { value: "vocabulary", label: "Vocabulary" },
];

export default async function GraphPage({ searchParams }: { searchParams: Promise<{ tab?: string; concept_id?: string; search?: string; focus?: string; depth?: string; candidates?: string }> }) {
  const params = await searchParams;
  const tab = params.tab || "map";
  const depth = Math.min(Math.max(Number(params.depth) || 2, 1), 3);
  const includeCandidates = params.candidates === "1";
  const [concepts, candidates, vocabulary, detail] = await Promise.all([
    listGraphConcepts({ state: "confirmed,candidate", search: params.search, limit: 50 }),
    listGraphEdges({ state: "candidate", limit: 50 }),
    listGraphVocabulary(),
    params.concept_id ? getGraphConcept(params.concept_id) : Promise.resolve(null),
  ]);
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Knowledge graph</h1>
      <nav className="mb-4 inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground">
        {TABS.map((item) => (
          <a
            key={item.value}
            href={`/graph?tab=${item.value}`}
            className={cn(
              "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all hover:text-foreground",
              tab === item.value && "bg-background text-foreground shadow"
            )}
          >
            {item.label}
          </a>
        ))}
      </nav>
      {detail ? <ConceptDetail concept={detail} /> : tab === "candidates" ? (
        <div>
          <h2 className="mb-2 text-lg font-semibold">Candidate review</h2>
          {candidates.items.length ? candidates.items.map((edge) => <CandidateEdgeRow key={edge.edge_id} edge={edge} evidenceEntityIds={edge.evidence_entity_ids} />) : <p className="text-sm text-muted-foreground">No candidate edges.</p>}
        </div>
      ) : tab === "vocabulary" ? (
        <div>
          <h2 className="mb-2 text-lg font-semibold">Vocabulary</h2>
          <VocabCreateForm />
          {vocabulary.map((item) => <VocabRow key={item.name} item={item} />)}
        </div>
      ) : tab === "map" ? (
        <div>
          <h2 className="mb-2 text-lg font-semibold">Map</h2>
          <GraphExplorer
            initialFocus={params.focus || concepts.items.find((c) => c.state === "confirmed")?.concept_id || concepts.items[0]?.concept_id || null}
            initialDepth={depth}
            initialCandidates={includeCandidates}
          />
        </div>
      ) : (
        <div>
          <h2 className="mb-2 text-lg font-semibold">Concepts</h2>
          <form className="mb-3 flex gap-2">
            <input type="hidden" name="tab" value="concepts" />
            <Input name="search" placeholder="Search concepts" defaultValue={params.search || ""} className="max-w-xs" />
            <Button variant="secondary">Search</Button>
          </form>
          {concepts.items.length ? concepts.items.map((concept) => <ConceptRow key={concept.concept_id} concept={concept} />) : <p className="text-sm text-muted-foreground">No concepts.</p>}
        </div>
      )}
    </section>
  );
}
