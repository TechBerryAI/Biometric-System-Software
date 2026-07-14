import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Attendance } from "@/features/attendance/pages/AttendancePage";
import { renderWithProviders } from "@test/setup/render";

describe("FE-UNIT-ATT-001 Attendance page", () => {
  it("renders attendance heading", async () => {
    renderWithProviders(<Attendance />, { withAuth: false, route: "/attendance" });
    expect(screen.getByRole("heading", { name: /attendance/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Ada Lovelace/i)).toBeInTheDocument();
    });
  });
});
