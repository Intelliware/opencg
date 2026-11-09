import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UnauthenticatedBanner } from "./UnauthenticatedBanner";

describe("UnauthenticatedBanner", () => {
  it("names the setting that enables authentication", () => {
    render(<UnauthenticatedBanner />);
    expect(screen.getByRole("status")).toHaveTextContent("OPENCG__ADMIN_UI__PASSWORD");
  });
});
