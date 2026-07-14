import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Sidebar } from "@/components/layout/Sidebar";
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

describe("FE-UNIT-SIDE-001 Sidebar", () => {
  it("renders brand, nav links, and sync action", async () => {
    renderWithProviders(<Sidebar />, { withAuth: false });
    expect(screen.getByText("Biometrica")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /employees/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /sync now/i })).toBeInTheDocument();
  });
});
