import type { Meta, StoryObj } from "@storybook/react";
import { CostBreakdown } from "./CostBreakdown";

const meta: Meta<typeof CostBreakdown> = {
  title: "Admin/CostBreakdown",
  component: CostBreakdown,
};
export default meta;

type Story = StoryObj<typeof CostBreakdown>;

const embed = { provider: "ollama", model: "nomic-embed-text", tokens_in: 18, tokens_out: 0, cost_usd: 0 };

export const Priced: Story = {
  args: {
    total: 0.000123,
    complete: true,
    providers: [embed, { provider: "ollama-cloud", model: "gpt-oss:20b", tokens_in: 410, tokens_out: 96, cost_usd: 0.000123 }],
  },
};

export const PricedAtZero: Story = {
  args: { total: 0, complete: true, providers: [embed] },
};

export const PartlyUnpriced: Story = {
  args: {
    total: 0,
    complete: false,
    providers: [embed, { provider: "ollama-cloud", model: "gemma3:4b", tokens_in: 410, tokens_out: 96, cost_usd: null }],
  },
};

export const PreChange: Story = {
  args: { total: null, providers: null },
};
