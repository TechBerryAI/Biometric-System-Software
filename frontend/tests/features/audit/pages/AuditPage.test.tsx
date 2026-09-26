import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Audit } from "@/features/audit/pages/AuditPage";
import { renderWithProviders } from "@test/setup/render";

describe("FE-UNIT-AUD-001 Audit page", () => {
  it("renders audit heading and empty correction state", async () => {
    renderWithProviders(<Audit />, { withAuth: false, route: "/audit" });
    expect(screen.getByRole("heading", { name: /^audit$/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/no device activity yet/i)).toBeInTheDocument();
    });
  });
});
