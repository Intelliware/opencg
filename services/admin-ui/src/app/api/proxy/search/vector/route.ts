// Next.js route handler that proxies POST /search/vector to the pipeline.
// Client components in the admin UI cannot reach the compose-internal pipeline
// URL directly, so this server route brokers the call.

import { vectorSearch } from "@/lib/api";
import { PipelineAuthError, authErrorResponse } from "@/lib/auth/errors";

export async function POST(req: Request) {
  const body = await req.json();
  let out;
  try {
    out = await vectorSearch(body);
  } catch (error) {
    if (error instanceof PipelineAuthError) return authErrorResponse(error);
    throw error;
  }
  if (out === null) {
    return Response.json({ error: "search failed" }, { status: 502 });
  }
  return Response.json(out, { status: 200 });
}
