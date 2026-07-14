import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Employees } from "@/features/employees/pages/EmployeesPage";
import { renderWithProviders } from "@test/setup/render";

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: { user_uuid: "1", email: "admin@company.com", role: "SUPER_ADMIN", active: true },
    loading: false,
    can: (p: string) => p === "employee:view" || p === "employee:edit",
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
    applyAuthTokens: vi.fn(),
  }),
}));

describe("FE-UNIT-EMP-001 Employees page", () => {
  it("renders employees heading and directory data", async () => {
    renderWithProviders(<Employees />, { withAuth: false, route: "/employees" });
    expect(screen.getByRole("heading", { name: /employees/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    });
  });
});
