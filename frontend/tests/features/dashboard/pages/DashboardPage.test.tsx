import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Dashboard } from "@/features/dashboard/pages/DashboardPage";
import { renderWithProviders } from "@test/setup/render";

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: {
      user_uuid: "usr_TESTADMIN000001",
      email: "admin@company.com",
      full_name: "Admin",
      role: "SUPER_ADMIN",
      active: true,
      capabilities: { attendance_adjust: true, forensic_audit: true },
    },
    loading: false,
    can: () => true,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
    applyAuthTokens: vi.fn(),
  }),
}));

vi.mock("@/features/dashboard/hooks/useDashboard", () => ({
  useDashboard: () => ({
    employees: [{ id: 1, name: "Ada", device_user_id: "1001", department: "Eng", shift_start: null, shift_end: null, created_at: "" }],
    summary: [],
    loading: false,
    error: null,
    reload: vi.fn(),
    presentToday: 0,
    absentToday: 0,
    totalEmployees: 1,
  }),
}));

vi.mock("@/features/attendance/hooks/useAttendanceTrend", () => ({
  useAttendanceTrend: () => ({
    data: [],
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/features/attendance/hooks/useRecentLogs", () => ({
  useRecentLogs: () => ({
    data: [],
    isLoading: false,
    error: null,
  }),
}));

describe("FE-UNIT-DASH-001 Dashboard", () => {
  it("renders the executive command center heading", async () => {
    renderWithProviders(<Dashboard />, { withAuth: false });
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /executive command center/i })).toBeInTheDocument();
    });
  });
});
