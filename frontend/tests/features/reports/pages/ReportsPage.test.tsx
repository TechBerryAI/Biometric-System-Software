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
  it("renders reports heading, export card, and Sort by control", () => {
    renderWithProviders(<Reports />, { withAuth: true, route: "/reports" });
    expect(screen.getByRole("heading", { name: /reports/i })).toBeInTheDocument();
    expect(screen.getByText(/report export/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/sort by/i)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /early first/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /late first/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /name a–z/i })).toBeInTheDocument();
  });
});
