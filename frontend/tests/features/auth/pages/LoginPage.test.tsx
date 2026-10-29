import axios from "axios";
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
    expect(screen.getByRole("link", { name: /forgot password/i })).toHaveAttribute("href", "/forgot-password");
    await user.type(screen.getByPlaceholderText("admin@company.com"), "admin@company.com");
    await user.type(screen.getByPlaceholderText("••••••••"), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith("admin@company.com", "password123");
    });
  });

  it("shows friendly text for a 401 without API detail (not status-code message)", async () => {
    const user = userEvent.setup();
    const err = new axios.AxiosError("Request failed with status code 401");
    err.response = {
      status: 401,
      statusText: "Unauthorized",
      headers: {},
      config: { headers: {} } as never,
      data: {},
    };
    loginMock.mockRejectedValue(err);
    renderWithProviders(<Login />, { withAuth: false, route: "/login" });

    await user.type(screen.getByPlaceholderText("admin@company.com"), "admin@company.com");
    await user.type(screen.getByPlaceholderText("••••••••"), "wrong-password");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText("Incorrect email or password.")).toBeInTheDocument();
    });
    expect(screen.queryByText(/Request failed with status code/i)).not.toBeInTheDocument();
  });
});
