import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { EmployeeProfile } from "@/features/employees/pages/EmployeeProfilePage";
import { renderWithProviders } from "@test/setup/render";

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: {
      user_uuid: "1",
      email: "admin@company.com",
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

describe("FE-UNIT-EMP-002 EmployeeProfile page", () => {
  it("loads and shows employee name", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/employees/:employeeId" element={<EmployeeProfile />} />
      </Routes>,
      { withAuth: false, route: "/employees/1" },
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Ada Lovelace" })).toBeInTheDocument();
    });
  });
});
