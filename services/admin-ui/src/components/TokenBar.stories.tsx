import type { Meta, StoryObj } from "@storybook/react";
import { TokenBar } from "./TokenBar";

const meta: Meta<typeof TokenBar> = {
  title: "Admin/TokenBar",
  component: TokenBar,
};
export default meta;

type Story = StoryObj<typeof TokenBar>;

export const Default: Story = { args: { tokens_in: 100, tokens_out: 25 } };
export const Compact: Story = { args: { tokens_in: 100, tokens_out: 25, compact: true } };
export const ZeroOut: Story = { args: { tokens_in: 500, tokens_out: 0 } };
export const Heavy: Story = { args: { tokens_in: 5_000, tokens_out: 1_200 } };
export const WithCost: Story = {
  args: { tokens_in: 213, tokens_out: 0, cost: { kind: "priced", total: 0.000123 } },
};
export const WithPricedAtZero: Story = {
  args: { tokens_in: 213, tokens_out: 0, cost: { kind: "priced", total: 0 } },
};
export const WithPartlyUnpricedCost: Story = {
  args: { tokens_in: 620, tokens_out: 96, cost: { kind: "partial", total: 0.0042 } },
};
export const WithPreChangeCost: Story = {
  args: { tokens_in: 213, tokens_out: 0, cost: { kind: "missing" } },
};
export const CompactWithCost: Story = {
  args: { tokens_in: 620, tokens_out: 96, compact: true, cost: { kind: "partial", total: 0.0042 } },
};
