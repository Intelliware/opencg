import { describe, expect, it } from "vitest";
import { formatUsd, summarizeCost } from "./cost";

describe("formatUsd", () => {
  it.each([
    [0.000123, "$0.000123"],
    [0.0001234567, "$0.0001235"],
    [1.234, "$1.234"],
    [1.23456, "$1.235"],
    [0.5, "$0.50"],
    [12, "$12.00"],
    [1234.5, "$1,235.00"],
    [0.0000001, "$0.0000001"],
  ])("formats %s as %s", (value, expected) => {
    expect(formatUsd(value)).toBe(expected);
  });

  it("shows zero as $0.00", () => {
    expect(formatUsd(0)).toBe("$0.00");
  });

  it("shows a missing cost as an em dash", () => {
    expect(formatUsd(null)).toBe("—");
    expect(formatUsd(undefined)).toBe("—");
    expect(formatUsd(Number.NaN)).toBe("—");
  });
});

const priced = { provider: "ollama", model: "nomic-embed-text", tokens_in: 12, tokens_out: 0, cost_usd: 0 };
const unpriced = { provider: "ollama-cloud", model: "gemma3:4b", tokens_in: 300, tokens_out: 80, cost_usd: null };

describe("summarizeCost", () => {
  it("is missing when neither total nor providers were recorded", () => {
    expect(summarizeCost(null, null)).toEqual({ kind: "missing" });
    expect(summarizeCost(undefined, undefined)).toEqual({ kind: "missing" });
    expect(summarizeCost(null, [])).toEqual({ kind: "missing" });
  });

  it("is priced when every provider has a price", () => {
    expect(summarizeCost(0.0012, [{ ...priced, cost_usd: 0.0012 }])).toEqual({ kind: "priced", total: 0.0012 });
  });

  it("is priced at zero for free local embeddings", () => {
    expect(summarizeCost(0, [priced])).toEqual({ kind: "priced", total: 0 });
  });

  it("is partial when any provider is unpriced", () => {
    expect(summarizeCost(0, [priced, unpriced])).toEqual({ kind: "partial", total: 0 });
  });

  it("is partial when the envelope says the cost is incomplete", () => {
    expect(summarizeCost(0.5, undefined, false)).toEqual({ kind: "partial", total: 0.5 });
  });

  it("falls back to the priced subtotal when the total is absent", () => {
    expect(summarizeCost(null, [{ ...priced, cost_usd: 0.002 }, unpriced])).toEqual({
      kind: "partial",
      total: 0.002,
    });
  });
});
