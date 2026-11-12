"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PermissionDenied } from "@/components/PermissionDenied";
import { checkProxyAuth } from "@/lib/proxy-client";

export function RunNowPanel() {
  const router = useRouter();
  const [repoUrl, setRepoUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [denied, setDenied] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const candidate = repoUrl.trim();
    // The ingestion service is the authority on which URLs are allowed
    // (https/ssh/git, public hosts, configured local roots); show its reason.
    if (!candidate) {
      setError("Enter a repository URL.");
      return;
    }
    setBusy(true);
    setError(null);
    setDenied(null);
    const res = await fetch("/api/proxy/ingestion/git/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ repo_url: candidate }),
    });
    setBusy(false);
    const auth = await checkProxyAuth(res, "start an ingestion run");
    if (auth.kind === "signin") return;
    if (auth.kind === "denied") {
      setDenied(auth.action);
      toast.error(auth.message);
      return;
    }
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      const message = body.error ?? `Run failed (${res.status})`;
      setError(message);
      toast.error(message);
      return;
    }
    toast.success("Ingestion run started");
    setRepoUrl("");
    router.refresh();
  };

  return (
    <Card>
      <CardContent className="p-3">
        <form onSubmit={submit} className="flex items-center gap-2">
          <Input
            type="text"
            name="repo_url"
            aria-label="Repository URL"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            autoComplete="off"
            spellCheck={false}
            className="flex-1"
          />
          <Button type="submit" disabled={busy} className={busy ? "cursor-wait" : ""}>
            {busy ? "Starting…" : "Run now"}
          </Button>
          {error ? (
            <span className="self-center text-xs text-red-600 dark:text-red-400">
              {error}
            </span>
          ) : null}
        </form>
        {denied ? <PermissionDenied action={denied} className="mt-3" /> : null}
      </CardContent>
    </Card>
  );
}
