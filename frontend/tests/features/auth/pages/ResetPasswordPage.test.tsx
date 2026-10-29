import axios from "axios";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResetPassword } from "@/features/auth/pages/ResetPasswordPage";
import { renderWithProviders } from "@test/setup/render";

const confirmPasswordResetMock = vi.fn();

vi.mock("@/features/auth/api", () => ({
  confirmPasswordReset: (...args: unknown[]) => confirmPasswordResetMock(...args),
}));

describe("FE-UNIT-RESET-001 Reset password page", () => {
  beforeEach(() => {
    confirmPasswordResetMock.mockReset();
  });

  it("shows an error when the reset token is missing", () => {
    renderWithProviders(<ResetPassword />, { withAuth: false, route: "/reset-password" });
    expect(screen.getByText(/reset link is missing or invalid/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request a new link/i })).toHaveAttribute("href", "/forgot-password");
    expect(confirmPasswordResetMock).not.toHaveBeenCalled();
  });

  it("submits a new password and shows success", async () => {
    const user = userEvent.setup();
    confirmPasswordResetMock.mockResolvedValue(undefined);
    renderWithProviders(<ResetPassword />, {
      withAuth: false,
      route: "/reset-password?token=abcdefghijklmnopqrstuvwxyz",
    });

    await user.type(screen.getByPlaceholderText("Minimum 8 characters"), "NewSecret123!");
    await user.type(screen.getByPlaceholderText("Re-enter new password"), "NewSecret123!");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(confirmPasswordResetMock).toHaveBeenCalledWith({
        token: "abcdefghijklmnopqrstuvwxyz",
        new_password: "NewSecret123!",
        confirm_password: "NewSecret123!",
      });
    });
    expect(screen.getByText(/your password has been updated/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });

  it("shows an API error for an expired token", async () => {
    const user = userEvent.setup();
    const err = new axios.AxiosError("Request failed");
    err.response = {
      status: 400,
      statusText: "Bad Request",
      headers: {},
      config: { headers: {} } as never,
      data: { detail: "Invalid or expired reset token" },
    };
    confirmPasswordResetMock.mockRejectedValue(err);
    renderWithProviders(<ResetPassword />, {
      withAuth: false,
      route: "/reset-password?token=abcdefghijklmnopqrstuvwxyz",
    });

    await user.type(screen.getByPlaceholderText("Minimum 8 characters"), "NewSecret123!");
    await user.type(screen.getByPlaceholderText("Re-enter new password"), "NewSecret123!");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(screen.getByText("Invalid or expired reset token")).toBeInTheDocument();
    });
  });
});
