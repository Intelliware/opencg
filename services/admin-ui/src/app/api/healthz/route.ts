// Liveness for the container healthcheck. Deliberately does not call the
// pipeline, so a pipeline outage does not mark the UI itself unhealthy.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" });
}
