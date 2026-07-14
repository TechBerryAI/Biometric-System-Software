import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { TopBar } from "@/components/layout/TopBar";
import { renderWithProviders } from "@test/setup/render";

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: {
      user_uuid: "1",
      email: "admin@company.com",
      full_name: "Admin User",
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

describe("FE-UNIT-TOPBAR-001 TopBar", () => {
  it("renders search and notifications bell stub (no notifications API)", () => {
    renderWithProviders(<TopBar />, { withAuth: false });
    expect(screen.getByLabelText("Search")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /notifications/i })).toBeInTheDocument();
  });
});
