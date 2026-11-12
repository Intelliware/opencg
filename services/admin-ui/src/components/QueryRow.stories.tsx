import type { Meta, StoryObj } from "@storybook/react";
import { QueryRow } from "./QueryRow";

const meta: Meta<typeof QueryRow> = {
  title: "Admin/QueryRow",
  component: QueryRow,
};
export default meta;

type Story = StoryObj<typeof QueryRow>;

const base = {
  id: 42,
  created_at: new Date("2026-06-10T12:34:56Z").toISOString(),
  principal: "local-dev",
  tool: "retrieve_for_context",
  query: "How do we connect a new model provider?",
  tokens_in: 128,
  tokens_out: 0,
  latency_ms: 215,
  outcome: "ok" as const,
};

export const Default: Story = { args: base };
export const Error: Story = { args: { ...base, outcome: "error", latency_ms: 5000 } };
export const LongQuery: Story = {
  args: {
    ...base,
    query:
      "Walk me through the entire 7-stage retrieval pipeline and explain where token accounting happens at each step in painful detail please",
  },
};
export const Priced: Story = {
  args: {
    ...base,
    estimated_cost_usd: 0.000123,
    usage_by_provider: [
      { provider: "ollama", model: "nomic-embed-text", tokens_in: 128, tokens_out: 0, cost_usd: 0.000123 },
    ],
  },
};
export const PricedAtZero: Story = {
  args: {
    ...base,
    estimated_cost_usd: 0,
    usage_by_provider: [
      { provider: "ollama", model: "nomic-embed-text", tokens_in: 128, tokens_out: 0, cost_usd: 0 },
    ],
  },
};
export const PartlyUnpriced: Story = {
  args: {
    ...base,
    tokens_in: 538,
    tokens_out: 96,
    estimated_cost_usd: 0,
    usage_by_provider: [
      { provider: "ollama", model: "nomic-embed-text", tokens_in: 128, tokens_out: 0, cost_usd: 0 },
      { provider: "ollama-cloud", model: "gemma3:4b", tokens_in: 410, tokens_out: 96, cost_usd: null },
    ],
  },
};
export const PreChange: Story = { args: { ...base, estimated_cost_usd: null, usage_by_provider: null } };
