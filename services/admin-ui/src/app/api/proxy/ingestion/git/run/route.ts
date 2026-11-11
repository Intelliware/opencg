import { runGit } from "@/lib/api";

const json = (body: unknown, status: number) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { repo_url?: string };
  if (!body.repo_url?.trim()) {
    return json({ error: "repo_url required" }, 400);
  }
  const out = await runGit(body.repo_url.trim());
  if (!out.ok) {
    return json({ error: out.message }, out.status);
  }
  return json(out.run, 200);
}
