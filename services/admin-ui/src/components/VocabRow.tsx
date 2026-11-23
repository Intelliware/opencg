"use client";

import type { RelationshipType } from "@opencg/shared";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { checkProxyAuth } from "@/lib/proxy-client";
import { RelationshipTypeBadge } from "./RelationshipTypeBadge";

async function call(url: string, init: RequestInit, action: string): Promise<boolean> {
  const auth = await checkProxyAuth(await fetch(url, init), action);
  if (auth.kind === "denied") toast.error(auth.message);
  return auth.kind === "ok";
}

export function VocabRow({ item }: { item: RelationshipType }) {
  const router = useRouter();
  const [description, setDescription] = useState(item.description);
  async function save() {
    const ok = await call(
      `/api/proxy/graph/vocab/${item.name}`,
      { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ description }) },
      "edit this relationship type",
    );
    if (ok) router.refresh();
  }
  async function deprecate() {
    const ok = await call(
      `/api/proxy/graph/vocab/${item.name}/deprecate`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ reason: "admin deprecation" }) },
      "deprecate this relationship type",
    );
    if (ok) router.refresh();
  }
  return (
    <div className="grid grid-cols-[160px_1fr_auto] items-center gap-3 border-b px-2 py-2.5 text-sm">
      <RelationshipTypeBadge type={item.name} />
      <Input aria-label={`${item.name} description`} value={description} onChange={(event) => setDescription(event.target.value)} className="h-8" />
      <span className="flex gap-1.5">
        <Button size="sm" variant="secondary" onClick={save}>Save</Button>
        <Button size="sm" variant="destructive" onClick={deprecate}>Deprecate</Button>
      </span>
    </div>
  );
}
