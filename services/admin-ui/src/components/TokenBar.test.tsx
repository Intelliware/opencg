import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TokenBar } from "./TokenBar";

describe("TokenBar", () => {
  it("exposes tokens via title attribute", () => {
    const { container } = render(<TokenBar tokens_in={120} tokens_out={30} />);
    const bar = container.querySelector('[title="in: 120, out: 30"]');
    expect(bar).not.toBeNull();
  });

  it("renders the numeric arrows in non-compact mode", () => {
    render(<TokenBar tokens_in={120} tokens_out={30} />);
    expect(screen.getByText("↑ 120")).toBeInTheDocument();
    expect(screen.getByText("↓ 30")).toBeInTheDocument();
  });

  it("omits the numeric arrows in compact mode", () => {
    render(<TokenBar tokens_in={120} tokens_out={30} compact />);
    expect(screen.queryByText("↑ 120")).toBeNull();
  });

  it("renders no cost line unless a cost is given", () => {
    render(<TokenBar tokens_in={120} tokens_out={30} />);
    expect(screen.queryByTestId("cost-value")).toBeNull();
  });

  it("renders the cost line when a cost is given", () => {
    render(<TokenBar tokens_in={120} tokens_out={30} cost={{ kind: "priced", total: 0.000123 }} />);
    expect(screen.getByText("$0.000123")).toBeInTheDocument();
  });

  it("renders an em dash for a cost that was not recorded", () => {
    render(<TokenBar tokens_in={120} tokens_out={30} cost={{ kind: "missing" }} compact />);
    expect(screen.getByTestId("cost-value")).toHaveTextContent("—");
  });
});
