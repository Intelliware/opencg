import { runGit } from "@/lib/api";
import { PipelineAuthError, authErrorResponse } from "@/lib/auth/errors";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { repo_url?: string };
  if (!body.repo_url?.trim()) {
    return Response.json({ error: "repo_url required" }, { status: 400 });
  }
  let out;
  try {
    out = await runGit(body.repo_url.trim());
  } catch (error) {
    if (error instanceof PipelineAuthError) return authErrorResponse(error);
    throw error;
  }
  if (!out.ok) {
    return Response.json({ error: out.message }, { status: out.status });
  }
  return Response.json(out.run, { status: 200 });
}
