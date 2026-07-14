import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Login } from "@/features/auth/pages/LoginPage";
import { renderWithProviders } from "@test/setup/render";

const loginMock = vi.fn();
const useAuthMock = vi.fn();

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => useAuthMock(),
}));

describe("FE-UNIT-LOGIN-001 Login page", () => {
  beforeEach(() => {
    loginMock.mockReset();
    useAuthMock.mockReturnValue({
      user: null,
      loading: false,
      login: loginMock,
      logout: vi.fn(),
      refreshUser: vi.fn(),
      applyAuthTokens: vi.fn(),
      can: () => false,
    });
  });

  it("renders sign-in form and submits credentials", async () => {
    const user = userEvent.setup();
    loginMock.mockResolvedValue(undefined);
    renderWithProviders(<Login />, { withAuth: false, route: "/login" });

    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("admin@company.com"), "admin@company.com");
    await user.type(screen.getByPlaceholderText("••••••••"), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith("admin@company.com", "password123");
    });
  });
});
