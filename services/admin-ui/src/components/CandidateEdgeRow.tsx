"use client";

import type { RelationshipEdge } from "@opencg/shared";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { checkProxyAuth } from "@/lib/proxy-client";
import { RelationshipTypeBadge } from "./RelationshipTypeBadge";

async function call(url: string, init: RequestInit, action: string): Promise<boolean> {
  const auth = await checkProxyAuth(await fetch(url, init), action);
  if (auth.kind === "denied") toast.error(auth.message);
  return auth.kind === "ok";
}

export function CandidateEdgeRow({ edge, evidenceEntityIds = [] }: { edge: RelationshipEdge; evidenceEntityIds?: string[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function action(name: "promote" | "demote") {
    setBusy(true);
    const ok = await call(
      `/api/proxy/graph/edges/${edge.edge_id}/${name}`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ reason: "admin review" }) },
      `${name} this relationship`,
    );
    setBusy(false);
    if (ok) router.refresh();
  }
  async function remove() {
    setBusy(true);
    const ok = await call(
      `/api/proxy/graph/edges/${edge.edge_id}`,
      { method: "DELETE", body: JSON.stringify({ reason: "admin review" }) },
      "tombstone this relationship",
    );
    setBusy(false);
    if (ok) router.refresh();
  }
  async function edit() {
    const type = window.prompt("Relationship type", edge.type);
    if (!type || type === edge.type) return;
    setBusy(true);
    const ok = await call(
      `/api/proxy/graph/edges/${edge.edge_id}`,
      { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ type, reason: "admin edit" }) },
      "edit this relationship",
    );
    setBusy(false);
    if (ok) router.refresh();
  }
  return (
    <div className="grid grid-cols-[130px_1fr_80px_auto] items-center gap-3 border-b px-2 py-2.5 text-sm">
      <RelationshipTypeBadge type={edge.type} />
      <span>
        {edge.from_concept_id} → {edge.to_concept_id}
        <br />
        {evidenceEntityIds.map((id) => (
          <a key={id} href={`/entities/${id}`} className="mr-2 text-primary underline-offset-4 hover:underline">
            evidence
          </a>
        ))}
      </span>
      <span className="text-muted-foreground">{edge.confidence.toFixed(2)}</span>
      <span className="flex gap-1.5">
        <Button size="sm" disabled={busy} onClick={() => action("promote")}>Promote</Button>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => action("demote")}>Demote</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={edit}>Edit</Button>
        <Button size="sm" variant="destructive" disabled={busy} onClick={remove}>Delete</Button>
      </span>
    </div>
  );
}
