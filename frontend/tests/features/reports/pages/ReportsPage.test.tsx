import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Reports } from "@/features/reports/pages/ReportsPage";
import { renderWithProviders } from "@test/setup/render";

vi.mock("@/features/attendance/hooks/useAttendanceTrend", () => ({
  useAttendanceTrend: () => ({
    data: [],
    isLoading: false,
    error: null,
  }),
}));

describe("FE-UNIT-REP-001 Reports page", () => {
  it("renders reports heading and export card", () => {
    renderWithProviders(<Reports />, { withAuth: false, route: "/reports" });
    expect(screen.getByRole("heading", { name: /reports/i })).toBeInTheDocument();
    expect(screen.getByText(/report export/i)).toBeInTheDocument();
  });
});
