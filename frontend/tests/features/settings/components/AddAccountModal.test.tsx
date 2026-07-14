import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { AddAccountModal } from "@/features/settings/components/AddAccountModal";
import { renderWithProviders } from "@test/setup/render";

describe("FE-UNIT-ACCT-001 AddAccountModal", () => {
  it("renders email, password, and role fields", () => {
    renderWithProviders(<AddAccountModal open onOpenChange={() => undefined} />, { withAuth: false });
    expect(screen.getByRole("heading", { name: /add account/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("name@company.com")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Minimum 8 characters")).toBeInTheDocument();
    expect(screen.getByText("Role")).toBeInTheDocument();
  });
});
