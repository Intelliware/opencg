// Client-side DELETE handler that proxies to the pipeline.

import { tombstoneEntity } from "@/lib/api";
import { PipelineAuthError, authErrorResponse } from "@/lib/auth/errors";

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  let out;
  try {
    out = await tombstoneEntity(id);
  } catch (error) {
    if (error instanceof PipelineAuthError) return authErrorResponse(error);
    throw error;
  }
  if (!out) {
    return Response.json({ error: "tombstone failed" }, { status: 502 });
  }
  return Response.json(out, { status: 200 });
}
