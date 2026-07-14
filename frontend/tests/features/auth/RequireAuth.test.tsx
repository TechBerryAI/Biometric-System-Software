import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { renderWithProviders } from "@test/setup/render";

const useAuthMock = vi.fn();

vi.mock("@/features/auth/AuthContext", async () => {
  const actual = await vi.importActual<typeof import("@/features/auth/AuthContext")>(
    "@/features/auth/AuthContext",
  );
  return {
    ...actual,
    useAuth: () => useAuthMock(),
  };
});

describe("FE-UNIT-GUARD-001 RequireAuth", () => {
  beforeEach(() => {
    useAuthMock.mockReset();
  });

  it("redirects to /login when there is no user", async () => {
    useAuthMock.mockReturnValue({
      user: null,
      loading: false,
      can: () => false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
      applyAuthTokens: vi.fn(),
    });

    renderWithProviders(
      <Routes>
        <Route
          path="/secure"
          element={
            <RequireAuth>
              <div>Secure content</div>
            </RequireAuth>
          }
        />
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>,
      { route: "/secure", withAuth: false },
    );

    await waitFor(() => {
      expect(screen.getByText("Login page")).toBeInTheDocument();
    });
    expect(screen.queryByText("Secure content")).not.toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    useAuthMock.mockReturnValue({
      user: { user_uuid: "1", email: "a@b.com", role: "SUPER_ADMIN", active: true },
      loading: false,
      can: () => true,
      login: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
      applyAuthTokens: vi.fn(),
    });

    renderWithProviders(
      <RequireAuth>
        <div>Secure content</div>
      </RequireAuth>,
      { withAuth: false },
    );

    expect(screen.getByText("Secure content")).toBeInTheDocument();
  });
});
