import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Settings } from "@/features/settings/pages/SettingsPage";
import { renderWithProviders } from "@test/setup/render";

const listFleetDevices = vi.fn();
const updateFleetDevice = vi.fn();

vi.mock("@/features/settings/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/settings/api")>("@/features/settings/api");
  return {
    ...actual,
    listFleetDevices: (...args: unknown[]) => listFleetDevices(...args),
    updateFleetDevice: (...args: unknown[]) => updateFleetDevice(...args),
  };
});

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    user: { user_uuid: "1", email: "admin@company.com", role: "SUPER_ADMIN", active: true },
    loading: false,
    can: () => true,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
    applyAuthTokens: vi.fn(),
  }),
}));

describe("FE-UNIT-SET-001 Settings page", () => {
  beforeEach(() => {
    listFleetDevices.mockReset();
    updateFleetDevice.mockReset();
    listFleetDevices.mockResolvedValue([
      {
        id: 1,
        device_uuid: "dev-1",
        name: "main-entrance",
        ip_address: "192.168.1.91",
        port: 4370,
        location: null,
        timezone: "Asia/Kolkata",
        branch_id: null,
        connectivity_mode: "both",
        firmware_version: null,
        serial_number: null,
        active: true,
        health_status: "ONLINE",
        mode: "NORMAL",
        last_seen: null,
        config_version: 1,
      },
    ]);
    updateFleetDevice.mockResolvedValue({
      id: 1,
      device_uuid: "dev-1",
      name: "main-entrance",
      ip_address: "192.168.1.100",
      port: 4370,
      location: null,
      timezone: "Asia/Kolkata",
      branch_id: null,
      connectivity_mode: "both",
      firmware_version: null,
      serial_number: null,
      active: true,
      health_status: "ONLINE",
      mode: "NORMAL",
      last_seen: null,
      config_version: 1,
    });
  });

  it("renders settings heading", async () => {
    renderWithProviders(<Settings />, { withAuth: false, route: "/settings" });
    expect(screen.getByRole("heading", { name: /settings/i })).toBeInTheDocument();
    expect(screen.getByText(/device bridge/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByDisplayValue("192.168.1.91")).toBeInTheDocument();
    });
  });

  it("saves editable device bridge fields", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Settings />, { withAuth: false, route: "/settings" });

    const ipInput = await screen.findByDisplayValue("192.168.1.91");
    await user.clear(ipInput);
    await user.type(ipInput, "192.168.1.100");

    await user.click(screen.getByRole("button", { name: /save device settings/i }));

    await waitFor(() => {
      expect(updateFleetDevice).toHaveBeenCalledWith("main-entrance", {
        ip_address: "192.168.1.100",
        port: 4370,
        timezone: "Asia/Kolkata",
      });
    });
    expect(await screen.findByText(/device connection settings saved/i)).toBeInTheDocument();
  });
});
