import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import App from "@/App";
import { renderWithProviders } from "@test/setup/render";

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: {
      user_uuid: "1",
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
    employees: [],
    summary: [],
    loading: false,
    error: null,
    reload: vi.fn(),
    presentToday: 0,
    absentToday: 0,
    totalEmployees: 0,
  }),
}));

vi.mock("@/features/attendance/hooks/useAttendanceTrend", () => ({
  useAttendanceTrend: () => ({ data: [], isLoading: false, error: null }),
}));

vi.mock("@/features/attendance/hooks/useRecentLogs", () => ({
  useRecentLogs: () => ({ data: [], isLoading: false, error: null }),
}));

describe("FE-UNIT-REDIR-001 legacy redirects", () => {
  it.each(["/corrections", "/raw-attendance", "/forensics", "/device-history"])(
    "redirects %s to Audit",
    async (path) => {
      renderWithProviders(<App />, { withAuth: false, route: path });
      await waitFor(() => {
        expect(screen.getByRole("heading", { name: /^audit$/i })).toBeInTheDocument();
      });
    },
  );
});
