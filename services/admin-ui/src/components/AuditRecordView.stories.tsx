import type { Meta, StoryObj } from "@storybook/react";
import { AuditRecordView } from "./AuditRecordView";

const meta: Meta<typeof AuditRecordView> = {
  title: "Admin/AuditRecordView",
  component: AuditRecordView,
};
export default meta;

type Story = StoryObj<typeof AuditRecordView>;

const sample = {
  id: 42,
  created_at: new Date("2026-06-10T12:34:56Z").toISOString(),
  correlation_id: "01HEXAMPLECORRELATIONID0001",
  tenant: "default",
  principal: "local-dev",
  roles: ["admin", "reader"],
  tool: "retrieve_for_context",
  query: "How does the audit log enforce immutability?",
  candidate_ids: ["e-1", "e-2", "e-3", "e-4", "e-5"],
  final_entity_ids: ["e-1", "e-3"],
  final_context_hash: "f6c5d4e3b2a1908070605040302010aafedcba9876543210123456789abcdef",
  tokens_in: 213,
  tokens_out: 0,
  latency_ms: 192,
  outcome: "ok" as const,
  error_code: null,
  estimated_cost_usd: 0,
  usage_by_provider: [
    { provider: "ollama", model: "nomic-embed-text", tokens_in: 213, tokens_out: 0, cost_usd: 0 },
  ],
};

export const Ok: Story = { args: { record: sample } };
export const Error: Story = {
  args: {
    record: {
      ...sample,
      outcome: "error",
      error_code: "pipeline_timeout",
      final_entity_ids: [],
    },
  },
};
export const PartlyUnpriced: Story = {
  args: {
    record: {
      ...sample,
      tokens_in: 623,
      tokens_out: 96,
      estimated_cost_usd: 0,
      usage_by_provider: [
        { provider: "ollama", model: "nomic-embed-text", tokens_in: 213, tokens_out: 0, cost_usd: 0 },
        { provider: "ollama-cloud", model: "gemma3:4b", tokens_in: 410, tokens_out: 96, cost_usd: null },
      ],
    },
  },
};
export const PreChange: Story = {
  args: { record: { ...sample, estimated_cost_usd: null, usage_by_provider: null } },
};
