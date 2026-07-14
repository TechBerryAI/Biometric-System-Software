import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { ChangePasswordCard } from "@/features/settings/components/ChangePasswordCard";
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

describe("FE-UNIT-PWD-001 ChangePasswordCard", () => {
  it("renders password fields", () => {
    renderWithProviders(<ChangePasswordCard />, { withAuth: false });
    expect(screen.getByText(/account security/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter current password")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Minimum 8 characters")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Re-enter new password")).toBeInTheDocument();
  });
});
