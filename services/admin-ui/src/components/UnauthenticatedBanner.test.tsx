import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UnauthenticatedBanner } from "./UnauthenticatedBanner";

describe("UnauthenticatedBanner", () => {
  it("points to OIDC mode, not the removed password gate", () => {
    render(<UnauthenticatedBanner />);
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("Unauthenticated mode");
    expect(banner).toHaveTextContent("OPENCG__AUTH__MODE=oidc");
    expect(banner).not.toHaveTextContent("OPENCG__ADMIN_UI__PASSWORD");
  });
});
