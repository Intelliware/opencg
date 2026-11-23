// Wording for permission-denied messages on graph proxy calls.

/** Human wording for the permission-denied message, from method + path. */
export function graphAction(method: string, path: string[]): string {
  const [resource, , verb] = path;
  if (method === "GET" || method === "HEAD") return "view the knowledge graph";
  const noun =
    resource === "edges" ? "relationship" : resource === "vocab" ? "relationship type" : "concept";
  if (verb === "promote" || verb === "demote" || verb === "deprecate") return `${verb} this ${noun}`;
  if (path[1] === "merge") return "merge concepts";
  if (method === "DELETE") return `tombstone this ${noun}`;
  if (method === "POST" && path.length === 1) return `create a ${noun}`;
  return `edit this ${noun}`;
}
