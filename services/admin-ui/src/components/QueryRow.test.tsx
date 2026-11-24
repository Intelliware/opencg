import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QueryRow } from "./QueryRow";

const base = {
  id: 42,
  created_at: new Date("2026-06-10T12:34:56Z").toISOString(),
  principal: "alice",
  tool: "retrieve_for_context",
  query: "test query",
  tokens_in: 100,
  tokens_out: 25,
  latency_ms: 215,
  outcome: "ok" as const,
};

describe("QueryRow", () => {
  it("renders principal, query, and outcome", () => {
    render(<QueryRow {...base} />);
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("test query")).toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("renders ERR when outcome is error", () => {
    render(<QueryRow {...base} outcome="error" />);
    expect(screen.getByText("ERR")).toBeInTheDocument();
  });

  it("links to the detail page", () => {
    render(<QueryRow {...base} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/queries/42");
  });

  it("shows an em dash when the row predates cost recording", () => {
    render(<QueryRow {...base} />);
    expect(screen.getByTestId("cost-value")).toHaveTextContent("—");
  });

  it("shows the estimated cost next to the tokens", () => {
    render(
      <QueryRow
        {...base}
        estimated_cost_usd={0}
        usage_by_provider={[
          { provider: "ollama", model: "nomic-embed-text", tokens_in: 100, tokens_out: 0, cost_usd: 0 },
        ]}
      />,
    );
    expect(screen.getByTestId("cost-value")).toHaveTextContent("$0.00");
  });

  it("marks a row with unpriced usage", () => {
    render(
      <QueryRow
        {...base}
        estimated_cost_usd={0.002}
        usage_by_provider={[
          { provider: "ollama", model: "nomic-embed-text", tokens_in: 100, tokens_out: 0, cost_usd: 0.002 },
          { provider: "ollama-cloud", model: "gemma3:4b", tokens_in: 10, tokens_out: 25, cost_usd: null },
        ]}
      />,
    );
    expect(screen.getByText("$0.002")).toBeInTheDocument();
    expect(screen.getByText("unpriced")).toBeInTheDocument();
  });
});
