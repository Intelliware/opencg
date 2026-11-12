import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CostBreakdown } from "./CostBreakdown";
import { CostValue } from "./CostValue";

const embed = { provider: "ollama", model: "nomic-embed-text", tokens_in: 18, tokens_out: 0, cost_usd: 0 };
const chat = { provider: "ollama-cloud", model: "gemma3:4b", tokens_in: 410, tokens_out: 96, cost_usd: null };

describe("CostBreakdown", () => {
  it("renders one row per provider and model with the total", () => {
    render(<CostBreakdown total={0.000123} providers={[{ ...embed, cost_usd: 0.000123 }]} />);
    const row = screen.getByRole("row", { name: /ollama nomic-embed-text/ });
    expect(within(row).getByText("18")).toBeInTheDocument();
    expect(within(row).getByText("$0.000123")).toBeInTheDocument();
    expect(within(screen.getByTestId("cost-total")).getByText("$0.000123")).toBeInTheDocument();
  });

  it("shows a zero price as $0.00", () => {
    render(<CostBreakdown total={0} providers={[embed]} />);
    expect(screen.getAllByText("$0.00")).toHaveLength(2);
    expect(screen.queryByText("unpriced")).toBeNull();
  });

  it("labels an unpriced row and marks the total as partial", () => {
    render(<CostBreakdown total={0} complete={false} providers={[embed, chat]} />);
    const row = screen.getByRole("row", { name: /ollama-cloud gemma3:4b/ });
    expect(within(row).getByText("unpriced")).toBeInTheDocument();
    const total = screen.getByTestId("cost-total");
    expect(within(total).getByText("unpriced")).toBeInTheDocument();
    expect(within(total).getByText("excludes unpriced usage")).toBeInTheDocument();
  });

  it("shows an em dash for rows written before cost was recorded", () => {
    render(<CostBreakdown total={null} providers={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("CostValue", () => {
  it("hides the note in compact mode but keeps the badge", () => {
    render(<CostValue summary={{ kind: "partial", total: 1.234 }} compact />);
    expect(screen.getByText("$1.234")).toBeInTheDocument();
    expect(screen.getByText("unpriced")).toBeInTheDocument();
    expect(screen.queryByText("excludes unpriced usage")).toBeNull();
  });
});
