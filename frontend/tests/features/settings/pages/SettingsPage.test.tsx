import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Settings } from "@/features/settings/pages/SettingsPage";
import { renderWithProviders } from "@test/setup/render";

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: { user_uuid: "1", email: "admin@company.com", role: "SUPER_ADMIN", active: true },
    loading: false,
    can: () => true,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
    applyAuthTokens: vi.fn(),
  }),
}));

describe("FE-UNIT-SET-001 Settings page", () => {
  it("renders settings heading", () => {
    renderWithProviders(<Settings />, { withAuth: false, route: "/settings" });
    expect(screen.getByRole("heading", { name: /settings/i })).toBeInTheDocument();
    expect(screen.getByText(/device bridge/i)).toBeInTheDocument();
  });
});
