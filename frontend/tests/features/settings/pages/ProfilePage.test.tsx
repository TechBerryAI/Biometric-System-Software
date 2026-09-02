import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Profile } from "@/features/settings/pages/ProfilePage";
import { renderWithProviders } from "@test/setup/render";

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: {
      user_uuid: "usr_TESTADMIN000001",
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

describe("FE-UNIT-PROF-001 Profile page", () => {
  it("renders profile heading and user email", () => {
    renderWithProviders(<Profile />, { withAuth: false, route: "/profile" });
    expect(screen.getByRole("heading", { name: /my profile/i })).toBeInTheDocument();
    expect(screen.getAllByText("admin@company.com").length).toBeGreaterThan(0);
  });
});
