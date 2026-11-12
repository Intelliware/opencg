"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Entity } from "@opencg/shared";
import { EntityDetail } from "@/components/EntityDetail";
import { PermissionDenied } from "@/components/PermissionDenied";
import { checkProxyAuth } from "@/lib/proxy-client";

export function EntityDetailView({ entity }: { entity: Entity }) {
  const router = useRouter();
  const [showFullBody, setShowFullBody] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [denied, setDenied] = useState<string | null>(null);

  const handleTombstone = async () => {
    if (!confirm("Soft-delete this entity? It will be excluded from future retrievals.")) {
      return;
    }
    setBusy(true);
    setError(null);
    setDenied(null);
    const res = await fetch(`/api/proxy/entities/${entity.entity_id}`, {
      method: "DELETE",
    });
    setBusy(false);
    const auth = await checkProxyAuth(res, "tombstone this entity");
    if (auth.kind === "signin") return;
    if (auth.kind === "denied") {
      setDenied(auth.action);
      return;
    }
    if (!res.ok) {
      setError(`Tombstone failed (${res.status})`);
      return;
    }
    router.refresh();
  };

  return (
    <>
      {denied ? <PermissionDenied action={denied} className="mb-3" /> : null}
      {error ? (
        <div className="mb-3 rounded-md border border-destructive/50 p-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      ) : null}
      <EntityDetail
        entity={entity}
        showFullBody={showFullBody}
        onToggleFullBody={() => setShowFullBody((v) => !v)}
        onTombstone={busy ? undefined : handleTombstone}
      />
    </>
  );
}
