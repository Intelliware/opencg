import type { Meta, StoryObj } from "@storybook/react";
import { CostValue } from "./CostValue";

const meta: Meta<typeof CostValue> = {
  title: "Admin/CostValue",
  component: CostValue,
};
export default meta;

type Story = StoryObj<typeof CostValue>;

export const Priced: Story = { args: { summary: { kind: "priced", total: 0.000123 } } };
export const PricedAtZero: Story = { args: { summary: { kind: "priced", total: 0 } } };
export const PartlyUnpriced: Story = { args: { summary: { kind: "partial", total: 0.0042 } } };
export const PartlyUnpricedCompact: Story = {
  args: { summary: { kind: "partial", total: 0.0042 }, compact: true },
};
export const PreChange: Story = { args: { summary: { kind: "missing" } } };
