import axios from "axios";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ForgotPassword } from "@/features/auth/pages/ForgotPasswordPage";
import { renderWithProviders } from "@test/setup/render";

const requestPasswordResetMock = vi.fn();

vi.mock("@/features/auth/api", () => ({
  requestPasswordReset: (...args: unknown[]) => requestPasswordResetMock(...args),
}));

describe("FE-UNIT-FORGOT-001 Forgot password page", () => {
  beforeEach(() => {
    requestPasswordResetMock.mockReset();
  });

  it("submits an email and offers to enter the OTP", async () => {
    const user = userEvent.setup();
    requestPasswordResetMock.mockResolvedValue(undefined);
    renderWithProviders(<ForgotPassword />, { withAuth: false, route: "/forgot-password" });

    expect(screen.getByRole("heading", { name: /forgot password/i })).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("admin@company.com"), "admin@company.com");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    await waitFor(() => {
      expect(requestPasswordResetMock).toHaveBeenCalledWith("admin@company.com");
    });
    expect(screen.getByText(/we sent a 6-digit code to admin@company.com/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /enter code/i })).toHaveAttribute(
      "href",
      "/reset-password?email=admin%40company.com"
    );
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
    renderWithProviders(<ForgotPassword />, { withAuth: false, route: "/forgot-password" });

    await user.type(screen.getByPlaceholderText("admin@company.com"), "unknown@company.com");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    await waitFor(() => {
      expect(screen.getByText("No account found for this email.")).toBeInTheDocument();
    });
    expect(screen.queryByText(/we sent a 6-digit code/i)).not.toBeInTheDocument();
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
    renderWithProviders(<ForgotPassword />, { withAuth: false, route: "/forgot-password" });

    await user.type(screen.getByPlaceholderText("admin@company.com"), "admin@company.com");
    await user.click(screen.getByRole("button", { name: /send verification code/i }));

    await waitFor(() => {
      expect(screen.getByText("Too many reset attempts")).toBeInTheDocument();
    });
  });
});
