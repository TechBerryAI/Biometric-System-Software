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

  it("submits email, OTP, and a new password", async () => {
    const user = userEvent.setup();
    confirmPasswordResetMock.mockResolvedValue(undefined);
    renderWithProviders(<ResetPassword />, {
      withAuth: false,
      route: "/reset-password?email=admin@company.com",
    });

    expect(screen.getByDisplayValue("admin@company.com")).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("6-digit code"), "847291");
    await user.type(screen.getByPlaceholderText("Minimum 8 characters"), "NewSecret123!");
    await user.type(screen.getByPlaceholderText("Re-enter new password"), "NewSecret123!");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(confirmPasswordResetMock).toHaveBeenCalledWith({
        email: "admin@company.com",
        otp: "847291",
        new_password: "NewSecret123!",
        confirm_password: "NewSecret123!",
      });
    });
    expect(screen.getByText(/your password has been updated/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });

  it("shows an API error for an expired OTP", async () => {
    const user = userEvent.setup();
    const err = new axios.AxiosError("Request failed");
    err.response = {
      status: 400,
      statusText: "Bad Request",
      headers: {},
      config: { headers: {} } as never,
      data: { detail: "Invalid or expired OTP" },
    };
    confirmPasswordResetMock.mockRejectedValue(err);
    renderWithProviders(<ResetPassword />, {
      withAuth: false,
      route: "/reset-password?email=admin@company.com",
    });

    await user.type(screen.getByPlaceholderText("6-digit code"), "847291");
    await user.type(screen.getByPlaceholderText("Minimum 8 characters"), "NewSecret123!");
    await user.type(screen.getByPlaceholderText("Re-enter new password"), "NewSecret123!");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(screen.getByText("Invalid or expired OTP")).toBeInTheDocument();
    });
  });
});
