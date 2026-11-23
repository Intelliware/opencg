"use client";

import type { ConceptListItem } from "@opencg/shared";
import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { checkProxyAuth } from "@/lib/proxy-client";

export function ConceptSearch({ onSelect }: { onSelect: (conceptId: string) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ConceptListItem[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets the debounced search when the query is emptied
      setResults([]);
      setSearched(false);
      setOpen(false);
      return;
    }
    let active = true;
    setLoading(true);
    const timer = setTimeout(() => {
      fetch(`/api/proxy/graph/concepts?search=${encodeURIComponent(q)}&limit=10`, { cache: "no-store" })
        .then(async (r) => {
          if (r.status === 401) await checkProxyAuth(r, "search concepts");
          return r.ok ? r.json() : { items: [] };
        })
        .then((data) => {
          if (!active) return;
          setResults(data.items ?? []);
          setSearched(true);
          setOpen(true);
        })
        .catch(() => active && setResults([]))
        .finally(() => active && setLoading(false));
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query]);

  function choose(conceptId: string) {
    onSelect(conceptId);
    setQuery("");
    setResults([]);
    setOpen(false);
    setSearched(false);
  }

  return (
    <div className="relative">
      <Input
        aria-label="Search concepts"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
        placeholder="Search concepts…"
        className="w-48"
      />
      {open ? (
        <ul className="absolute z-10 mt-1 max-h-64 w-64 overflow-auto rounded-md border bg-popover text-sm shadow-md">
          {results.length ? (
            results.map((concept) => (
              <li key={concept.concept_id}>
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(concept.concept_id)}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-accent"
                >
                  <span className="min-w-0 truncate">{concept.name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">{concept.state}</span>
                </button>
              </li>
            ))
          ) : searched && !loading ? (
            <li className="px-3 py-2 text-muted-foreground">No matches</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
