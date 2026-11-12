import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("@/components/ThemeToggle", () => ({ ThemeToggle: () => null }));

import { Sidebar } from "./Sidebar";

describe("Sidebar", () => {
  it("renders nav links in the configured order with Graph second", () => {
    render(<Sidebar />);
    const labels = screen.getAllByRole("link").map((link) => link.textContent?.trim());
    expect(labels).toEqual(["Overview", "Graph", "Vectors", "Entities", "Queries", "Ingestion"]);
    expect(labels[1]).toBe("Graph");
  });

  it("shows no user and no sign-out in none mode", () => {
    render(<Sidebar />);
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
    expect(screen.queryByLabelText(/Signed in as/)).toBeNull();
  });

  it("shows the signed-in principal and a sign-out form in oidc mode", () => {
    render(<Sidebar user={{ principal: "alice", roles: ["admin"] }} />);
    expect(screen.getByLabelText("Signed in as alice")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Sign out" });
    expect(button.closest("form")).toHaveAttribute("action", "/api/auth/signout");
    expect(button.closest("form")).toHaveAttribute("method", "post");
  });
});
