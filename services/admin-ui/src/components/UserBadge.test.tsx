import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UserBadge } from "./UserBadge";

describe("UserBadge", () => {
  it("shows the principal and roles", () => {
    render(<UserBadge principal="alice" roles={["admin", "reader"]} />);
    expect(screen.getByLabelText("Signed in as alice")).toHaveTextContent("alice");
    expect(screen.getByText("admin, reader")).toBeInTheDocument();
  });

  it("says when the principal has no roles", () => {
    render(<UserBadge principal="carol" roles={[]} />);
    expect(screen.getByText("no roles")).toBeInTheDocument();
  });
});
