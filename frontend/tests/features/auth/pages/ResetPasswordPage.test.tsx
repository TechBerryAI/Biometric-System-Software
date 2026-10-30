import axios from "axios";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResetPassword } from "@/features/auth/pages/ResetPasswordPage";
import { renderWithProviders } from "@test/setup/render";

const confirmPasswordResetMock = vi.fn();

vi.mock("@/features/auth/api", () => ({
  confirmPasswordReset: (...args: unknown[]) => confirmPasswordResetMock(...args),
}));

function renderResetPassword() {
  return renderWithProviders(
    <Routes>
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/login" element={<h1>Sign in</h1>} />
    </Routes>,
    { withAuth: false, route: "/reset-password?email=admin@company.com" }
  );
}

describe("FE-UNIT-RESET-001 Reset password page", () => {
  beforeEach(() => {
    confirmPasswordResetMock.mockReset();
  });

  it("resets the password then returns to sign in", async () => {
    const user = userEvent.setup();
    confirmPasswordResetMock.mockResolvedValue(undefined);
    renderResetPassword();

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
    expect(screen.getByRole("heading", { name: /^password reset$/i })).toBeInTheDocument();
    expect(screen.queryByText(/we sent a 6-digit code/i)).not.toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
      },
      { timeout: 2500 }
    );
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
    renderResetPassword();

    await user.type(screen.getByPlaceholderText("6-digit code"), "847291");
    await user.type(screen.getByPlaceholderText("Minimum 8 characters"), "NewSecret123!");
    await user.type(screen.getByPlaceholderText("Re-enter new password"), "NewSecret123!");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(screen.getByText("Invalid or expired OTP")).toBeInTheDocument();
    });
  });

  it("shows an API error when the new password matches the current one", async () => {
    const user = userEvent.setup();
    const err = new axios.AxiosError("Request failed");
    err.response = {
      status: 400,
      statusText: "Bad Request",
      headers: {},
      config: { headers: {} } as never,
      data: { detail: "New password must differ from current password" },
    };
    confirmPasswordResetMock.mockRejectedValue(err);
    renderResetPassword();

    await user.type(screen.getByPlaceholderText("6-digit code"), "847291");
    await user.type(screen.getByPlaceholderText("Minimum 8 characters"), "Secret123!");
    await user.type(screen.getByPlaceholderText("Re-enter new password"), "Secret123!");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(screen.getByText("New password must differ from current password")).toBeInTheDocument();
    });
  });
});
