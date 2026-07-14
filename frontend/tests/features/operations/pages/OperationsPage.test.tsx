import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Operations } from "@/features/operations/pages/OperationsPage";
import { renderWithProviders } from "@test/setup/render";

describe("FE-UNIT-OPS-001 Operations page", () => {
  it("renders operations center and metric cards", async () => {
    renderWithProviders(<Operations />, { withAuth: false, route: "/operations" });
    expect(screen.getByRole("heading", { name: /operations center/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Queue depth")).toBeInTheDocument();
    });
  });
});
