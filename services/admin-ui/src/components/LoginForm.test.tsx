import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LoginForm } from "./LoginForm";

describe("LoginForm", () => {
  it("posts the password and next path to the login route", () => {
    const { container } = render(<LoginForm next="/graph" />);
    const form = container.querySelector("form")!;
    expect(form).toHaveAttribute("action", "/api/auth/login");
    expect(form).toHaveAttribute("method", "post");
    expect(container.querySelector('input[name="next"]')).toHaveValue("/graph");
    expect(screen.getByLabelText("Access password")).toHaveAttribute("type", "password");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows an error for an incorrect password", () => {
    render(<LoginForm next="/" error />);
    expect(screen.getByRole("alert")).toHaveTextContent("Incorrect password.");
  });
});
