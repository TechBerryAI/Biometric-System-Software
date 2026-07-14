import { describe, expect, it, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAuth } from "@/features/auth/AuthContext";
import { renderWithProviders } from "@test/setup/render";

function AuthProbe() {
  const { user, loading, login, can } = useAuth();
  if (loading) return <p>Loading session...</p>;
  return (
    <div>
      <p data-testid="email">{user?.email ?? "none"}</p>
      <p data-testid="can-dash">{String(can("dashboard:view"))}</p>
      <button type="button" onClick={() => void login("admin@company.com", "secret")}>
        Login
      </button>
    </div>
  );
}

describe("FE-UNIT-AUTH-CTX-001 AuthContext", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders provider and logs in via mocked API", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AuthProbe />, { withAuth: true });

    expect(await screen.findByTestId("email")).toHaveTextContent("none");

    await user.click(screen.getByRole("button", { name: "Login" }));

    await waitFor(() => {
      expect(screen.getByTestId("email")).toHaveTextContent("admin@company.com");
    });
    expect(screen.getByTestId("can-dash")).toHaveTextContent("true");
  });
});
