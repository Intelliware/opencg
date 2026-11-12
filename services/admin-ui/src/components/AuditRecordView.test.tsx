import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AuditRecordView } from "./AuditRecordView";

const record = {
  id: 7,
  created_at: new Date("2026-06-10T12:34:56Z").toISOString(),
  correlation_id: "corr-7",
  tenant: "default",
  principal: "local-dev",
  roles: ["reader"],
  tool: "retrieve_for_context",
  query: "q",
  candidate_ids: ["e-1"],
  final_entity_ids: ["e-1"],
  final_context_hash: "f6c5d4e3b2a1908070605040302010aa",
  tokens_in: 12,
  tokens_out: 0,
  latency_ms: 40,
  outcome: "ok" as const,
};

describe("AuditRecordView cost", () => {
  it("shows the total and one breakdown row per provider and model", () => {
    render(
      <AuditRecordView
        record={{
          ...record,
          estimated_cost_usd: 0,
          usage_by_provider: [
            { provider: "ollama", model: "nomic-embed-text", tokens_in: 12, tokens_out: 0, cost_usd: 0 },
          ],
        }}
      />,
    );
    expect(screen.getByRole("row", { name: /ollama nomic-embed-text/ })).toBeInTheDocument();
    expect(within(screen.getByTestId("cost-total")).getByText("$0.00")).toBeInTheDocument();
  });

  it("renders a row written before cost was recorded with an em dash", () => {
    render(<AuditRecordView record={{ ...record, estimated_cost_usd: null, usage_by_provider: null }} />);
    expect(within(screen.getByTestId("cost-breakdown")).getByText("—")).toBeInTheDocument();
  });
});
