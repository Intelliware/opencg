import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PermissionDenied } from "./PermissionDenied";

describe("PermissionDenied", () => {
  it("names the denied action", () => {
    render(<PermissionDenied action="tombstone this entity" />);
    expect(screen.getByRole("alert")).toHaveTextContent("You don't have permission to tombstone this entity.");
  });

  it("shows a custom detail line", () => {
    render(<PermissionDenied action="view this page" detail="No role." />);
    expect(screen.getByRole("alert")).toHaveTextContent("No role.");
  });
});
