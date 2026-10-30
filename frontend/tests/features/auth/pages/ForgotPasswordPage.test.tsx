import axios from "axios";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ForgotPassword } from "@/features/auth/pages/ForgotPasswordPage";
import { renderWithProviders } from "@test/setup/render";

const requestPasswordResetMock = vi.fn();

vi.mock("@/features/auth/api", () => ({
  requestPasswordReset: (...args: unknown[]) => requestPasswordResetMock(...args),
}));

function renderForgotPassword() {
  return renderWithProviders(
    <Routes>
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<h1>Reset password</h1>} />
    </Routes>,
    { withAuth: false, route: "/forgot-password" }
  );
}

describe("FE-UNIT-FORGOT-001 Forgot password page", () => {
  beforeEach(() => {
    requestPasswordResetMock.mockReset();
  });

  it("submits an email and goes to the reset form", async () => {
    const user = userEvent.setup();
    requestPasswordResetMock.mockResolvedValue(undefined);
    renderForgotPassword();

    expect(screen.getByRole("heading", { name: /forgot password/i })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("admin@company.com"), "admin@company.com");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    await waitFor(() => {
      expect(requestPasswordResetMock).toHaveBeenCalledWith("admin@company.com");
    });
    expect(screen.getByRole("heading", { name: /reset password/i })).toBeInTheDocument();
    expect(screen.queryByText(/we sent a 6-digit code/i)).not.toBeInTheDocument();
  });

  it("shows an error when the account is not in the system", async () => {
    const user = userEvent.setup();
    const err = new axios.AxiosError("Request failed");
    err.response = {
      status: 404,
      statusText: "Not Found",
      headers: {},
      config: { headers: {} } as never,
      data: { detail: "No account found for this email." },
    };
    requestPasswordResetMock.mockRejectedValue(err);
    renderForgotPassword();

    await user.type(screen.getByPlaceholderText("admin@company.com"), "unknown@company.com");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    await waitFor(() => {
      expect(screen.getByText("No account found for this email.")).toBeInTheDocument();
    });
    expect(screen.queryByRole("heading", { name: /^reset password$/i })).not.toBeInTheDocument();
  });

  it("shows an API error when the request fails", async () => {
    const user = userEvent.setup();
    const err = new axios.AxiosError("Request failed");
    err.response = {
      status: 429,
      statusText: "Too Many Requests",
      headers: {},
      config: { headers: {} } as never,
      data: { detail: "Too many reset attempts" },
    };
    requestPasswordResetMock.mockRejectedValue(err);
    renderForgotPassword();

    await user.type(screen.getByPlaceholderText("admin@company.com"), "admin@company.com");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    await waitFor(() => {
      expect(screen.getByText("Too many reset attempts")).toBeInTheDocument();
    });
  });
});
