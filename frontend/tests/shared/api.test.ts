import axios from "axios";
import { describe, expect, it } from "vitest";
import { fetchEmployees } from "@/features/employees/api";
import { fetchOperationalMetrics } from "@/features/operations/api";
import { formatSyncErrorMessage, getApiErrorMessage } from "@/shared/api/client";
import { confirmPasswordReset, loginWithPassword, requestPasswordReset } from "@/features/auth/api";
import { mockTokens } from "@test/msw/handlers";

describe("FE-UNIT-API-001 api helpers", () => {
  it("FE-UNIT-API-001 extracts FastAPI detail strings via getApiErrorMessage", () => {
    const err = new axios.AxiosError("Request failed");
    err.response = {
      status: 400,
      statusText: "Bad Request",
      headers: {},
      config: { headers: {} } as never,
      data: { detail: "Invalid credentials" },
    };
    expect(getApiErrorMessage(err)).toBe("Invalid credentials");
  });

  it("formats sync offline guidance via formatSyncErrorMessage", () => {
    const err = new Error("connect failed: no route to host");
    expect(formatSyncErrorMessage(err)).toContain("adjust attendance manually");
  });

  it("explains 504 gateway timeouts on sync", () => {
    const err = new axios.AxiosError("Request failed with status code 504");
    err.response = {
      status: 504,
      statusText: "Gateway Timeout",
      headers: {},
      config: { headers: {} } as never,
      data: {},
    };
    expect(formatSyncErrorMessage(err)).toContain("proxy timed out");
  });

  it("requests a password reset through MSW", async () => {
    await expect(requestPasswordReset("admin@company.com")).resolves.toBeUndefined();
    await expect(
      confirmPasswordReset({
        email: "admin@company.com",
        otp: "847291",
        new_password: "NewSecret123!",
        confirm_password: "NewSecret123!",
      })
    ).resolves.toBeUndefined();
  });

  it("logs in through MSW-backed loginWithPassword", async () => {
    const tokens = await loginWithPassword("admin@company.com", "secret");
    if (!("access_token" in tokens)) throw new Error("Expected tokens, got an MFA challenge");
    expect(tokens.access_token).toBe(mockTokens.access_token);
    expect(tokens.refresh_token).toBe(mockTokens.refresh_token);
  });

  it("FE-UNIT-API-002 fetches employees and ops metrics via MSW contract", async () => {
    const employees = await fetchEmployees();
    expect(employees).toHaveLength(1);
    expect(employees[0].name).toBe("Ada Lovelace");

    const metrics = await fetchOperationalMetrics();
    expect(metrics.queue_depth).toBe(0);
    expect(metrics.device_health_status).toBe("ONLINE");
  });
});
