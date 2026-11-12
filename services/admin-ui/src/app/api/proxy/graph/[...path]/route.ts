import { NextRequest, NextResponse } from "next/server";

import { pipelineFetch } from "@/lib/api";
import { PipelineAuthError, authErrorResponse } from "@/lib/auth/errors";
import { graphAction } from "@/lib/graph-actions";

async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();
  let response: Response;
  try {
    response = await pipelineFetch(
      `/graph/${path.join("/")}${request.nextUrl.search}`,
      graphAction(request.method, path),
      {
        method: request.method,
        headers: body ? { "content-type": "application/json" } : undefined,
        body: body || undefined,
      },
    );
  } catch (error) {
    if (error instanceof PipelineAuthError) return authErrorResponse(error);
    throw error;
  }
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") || "application/json" },
  });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;
