"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ConceptDetail as ConceptDetailType } from "@opencg/shared";
import type { ForceGraphMethods, NodeObject, LinkObject } from "react-force-graph-2d";
import { ConceptDetail } from "@/components/ConceptDetail";
import { ConceptSearch } from "@/components/ConceptSearch";
import { Button } from "@/components/ui/button";
import { buildGraphModel, labelVisibility, type GraphNode, type TraverseData } from "./graph-model";
import { checkProxyAuth } from "@/lib/proxy-client";

type FgNode = NodeObject<GraphNode>;
type FgLink = LinkObject<GraphNode, { type: string; state: string }>;

const DEGREE_THRESHOLD = 4;
const ZOOM_LABEL_ALL = 1.5;

const COLORS = {
  confirmed: "#10b981",
  candidate: "#f59e0b",
  linkConfirmed: { dark: "#475569", light: "#cbd5e1" },
  linkCandidate: "#f59e0b",
  label: { dark: "#e5e7eb", light: "#374151" },
  ring: { dark: "#f8fafc", light: "#0f172a" },
};

function isDark() {
  return typeof document !== "undefined" && document.documentElement.classList.contains("dark");
}

async function fetchTraverse(
  conceptId: string,
  depth: number,
  includeCandidates: boolean,
): Promise<TraverseData> {
  const qs = new URLSearchParams({ concept_id: conceptId, depth: String(depth) });
  if (includeCandidates) qs.set("include_candidates", "true");
  const res = await fetch(`/api/proxy/graph/traverse?${qs}`, { cache: "no-store" });
  const auth = await checkProxyAuth(res, "explore the graph");
  if (auth.kind === "denied") throw new Error(auth.message);
  if (!res.ok) throw new Error(`traverse failed (${res.status})`);
  return (await res.json()) as TraverseData;
}

async function fetchDetail(conceptId: string): Promise<ConceptDetailType | null> {
  const res = await fetch(`/api/proxy/graph/concepts/${conceptId}`, { cache: "no-store" });
  await checkProxyAuth(res, "view this concept");
  if (!res.ok) return null;
  return (await res.json()) as ConceptDetailType;
}

function syncUrl(focus: string, depth: number, includeCandidates: boolean) {
  const qs = new URLSearchParams(window.location.search);
  qs.set("tab", "map");
  qs.set("focus", focus);
  qs.set("depth", String(depth));
  if (includeCandidates) qs.set("candidates", "1");
  else qs.delete("candidates");
  window.history.replaceState(null, "", `${window.location.pathname}?${qs}`);
}

export function GraphExplorer({
  initialFocus,
  initialDepth,
  initialCandidates,
}: {
  initialFocus: string | null;
  initialDepth: number;
  initialCandidates: boolean;
}) {
  const [focus, setFocus] = useState<string | null>(initialFocus);
  const [depth, setDepth] = useState(initialDepth);
  const [includeCandidates, setIncludeCandidates] = useState(initialCandidates);
  const [data, setData] = useState<TraverseData>({ nodes: [], edges: [] });
  const [detail, setDetail] = useState<ConceptDetailType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [hoverId, setHoverId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(initialFocus);

  // Load the force-graph component on the client only (it touches `window`).
  const [FG, setFG] = useState<React.ComponentType<Record<string, unknown>> | null>(null);
  useEffect(() => {
    let active = true;
    import("react-force-graph-2d").then((mod) => {
      if (active) setFG(() => mod.default as unknown as React.ComponentType<Record<string, unknown>>);
    });
    return () => {
      active = false;
    };
  }, []);

  const fgRef = useRef<ForceGraphMethods<FgNode, FgLink> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 800, height: 560 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      setSize({ width: el.clientWidth, height: el.clientHeight });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Fetch the neighbourhood whenever the focus / depth / candidate filter changes.
  useEffect(() => {
    if (!focus) return;
    // Sync before fetching: a replaceState that lands after a slow traverse can
    // override a sidebar navigation the user started in the meantime.
    syncUrl(focus, depth, includeCandidates);
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading flag for the fetch this effect starts; the result arrives asynchronously
    setLoading(true);
    setError(null);
    fetchTraverse(focus, depth, includeCandidates)
      .then((traverse) => {
        if (!active) return;
        setData(traverse);
      })
      .catch((e: unknown) => active && setError(e instanceof Error ? e.message : "traverse failed"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [focus, depth, includeCandidates]);

  // Load the detail card for the selected concept.
  useEffect(() => {
    if (!selectedId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clears the detail card when the selection is cleared; no fetch to run
      setDetail(null);
      return;
    }
    let active = true;
    fetchDetail(selectedId).then((d) => active && setDetail(d));
    return () => {
      active = false;
    };
  }, [selectedId]);

  const model = useMemo(() => buildGraphModel(data, focus), [data, focus]);

  // force-graph mutates node/link objects, so hand it fresh clones each change.
  const graphData = useMemo(
    () => ({
      nodes: model.nodes.map((n) => ({ ...n })),
      links: model.links.map((l) => ({ ...l })),
    }),
    [model],
  );

  // Zoom-independent label set; the zoom rule is applied per frame below.
  const baseLabels = useMemo(
    () => labelVisibility(model, { focusId: focus, selectedId, hoverId, degreeThreshold: DEGREE_THRESHOLD }),
    [model, focus, selectedId, hoverId],
  );

  const neighbours = useMemo(
    () => (hoverId ? model.adjacency.get(hoverId) ?? new Set<string>() : null),
    [model, hoverId],
  );

  const drawNode = useCallback(
    (node: FgNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const dark = isDark();
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const radius = node.isFocus ? 7 : 3 + Math.min(node.degree, 8) * 0.6;
      const dim = neighbours && node.id !== hoverId && !neighbours.has(node.id);

      ctx.globalAlpha = dim ? 0.25 : 1;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = node.state === "candidate" ? COLORS.candidate : COLORS.confirmed;
      ctx.fill();
      if (node.isFocus) {
        ctx.lineWidth = 2 / globalScale;
        ctx.strokeStyle = dark ? COLORS.ring.dark : COLORS.ring.light;
        ctx.stroke();
      }

      if (globalScale >= ZOOM_LABEL_ALL || baseLabels.has(node.id)) {
        const fontSize = Math.max(10 / globalScale, 2.5);
        ctx.font = `${node.isFocus ? "bold " : ""}${fontSize}px ui-sans-serif, system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = dark ? COLORS.label.dark : COLORS.label.light;
        ctx.fillText(node.name, x, y + radius + 1);
      }
      ctx.globalAlpha = 1;
    },
    [baseLabels, neighbours, hoverId],
  );

  const linkColor = useCallback(
    (link: FgLink) => {
      const dark = isDark();
      if (link.state === "candidate") return COLORS.linkCandidate;
      return dark ? COLORS.linkConfirmed.dark : COLORS.linkConfirmed.light;
    },
    [],
  );

  const linkDash = useCallback(
    (link: FgLink) => (link.state === "candidate" ? [3, 3] : null),
    [],
  );

  // Focusing a concept (node click, search pick, or neighbour navigation) both
  // selects it (loads detail) and re-seeds the traversal around it.
  const focusConcept = useCallback((conceptId: string) => {
    setSelectedId(conceptId);
    setFocus(conceptId);
  }, []);

  const onNodeClick = useCallback((node: FgNode) => focusConcept(node.id), [focusConcept]);

  const onEngineStop = useCallback(() => {
    fgRef.current?.zoomToFit(400, 60);
  }, []);

  if (!focus) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        No concept to explore yet. Add concepts on the Concepts tab, then open the Map.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 lg:flex-row">
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">Depth</span>
          {[1, 2, 3].map((d) => (
            <Button
              key={d}
              size="sm"
              variant={depth === d ? "default" : "outline"}
              onClick={() => setDepth(d)}
            >
              {d}
            </Button>
          ))}
          <Button
            size="sm"
            variant={includeCandidates ? "default" : "outline"}
            onClick={() => setIncludeCandidates((v) => !v)}
          >
            {includeCandidates ? "Candidates: on" : "Candidates: off"}
          </Button>
          {loading ? <span className="text-xs text-muted-foreground">Loading…</span> : null}
          {error ? <span className="text-xs text-destructive">{error}</span> : null}
          <div className="ml-auto">
            <ConceptSearch onSelect={focusConcept} />
          </div>
        </div>
        <div
          ref={containerRef}
          className="h-[560px] w-full overflow-hidden rounded-lg border bg-muted/20"
        >
          {FG && !error ? (
            <FG
              ref={fgRef as unknown as React.Ref<unknown>}
              graphData={graphData}
              width={size.width}
              height={size.height}
              nodeId="id"
              nodeRelSize={4}
              nodeCanvasObject={drawNode}
              nodePointerAreaPaint={(node: FgNode, color: string, ctx: CanvasRenderingContext2D) => {
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(node.x ?? 0, node.y ?? 0, 8, 0, 2 * Math.PI);
                ctx.fill();
              }}
              linkColor={linkColor}
              linkLineDash={linkDash}
              linkWidth={1}
              linkDirectionalArrowLength={3}
              linkDirectionalArrowRelPos={1}
              onNodeClick={onNodeClick}
              onNodeHover={(node: FgNode | null) => setHoverId(node ? node.id : null)}
              onEngineStop={onEngineStop}
              cooldownTicks={120}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {error ? "Could not load the graph." : "Preparing graph…"}
            </div>
          )}
        </div>
      </div>
      {detail ? (
        <aside className="w-full shrink-0 lg:w-80">
          <ConceptDetail concept={detail} onNavigate={focusConcept} />
        </aside>
      ) : null}
    </div>
  );
}
