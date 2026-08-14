import { api, configureApiAuth } from "@/shared/api/client";
import type { AccountCreatePayload, AuthTokens, CurrentUserResponse } from "@/features/auth/api";

export async function createAppAccount(payload: AccountCreatePayload): Promise<CurrentUserResponse> {
  const normalized = {
    email: payload.email.trim().toLowerCase(),
    full_name: payload.full_name?.trim() || null,
    password: payload.password,
    role: payload.role,
    active: payload.active ?? true,
  };
  const { data } = await api.post<CurrentUserResponse>("/auth/users", normalized);
  return data;
}

export async function updateMyProfile(payload: { full_name: string }): Promise<CurrentUserResponse> {
  const { data } = await api.put<CurrentUserResponse>("/auth/me", {
    full_name: payload.full_name.trim(),
  });
  return data;
}

export async function changeMyPassword(payload: {
  current_password: string;
  new_password: string;
  confirm_password: string;
}): Promise<AuthTokens> {
  const { data } = await api.post<AuthTokens>("/auth/me/password", payload);
  configureApiAuth(data.access_token);
  return data;
}

export type FleetDevice = {
  id: number;
  device_uuid: string;
  name: string;
  ip_address: string;
  port: number;
  location: string | null;
  timezone: string;
  branch_id: string | null;
  connectivity_mode: string;
  firmware_version: string | null;
  serial_number: string | null;
  active: boolean;
  health_status: string;
  mode: string;
  last_seen: string | null;
  config_version: number;
};

export type DeviceBridgeUpdate = {
  ip_address: string;
  port: number;
  timezone: string;
};

export async function listFleetDevices(): Promise<FleetDevice[]> {
  const { data } = await api.get<FleetDevice[]>("/devices", {
    params: { active_only: true },
  });
  return data;
}

export async function updateFleetDevice(
  deviceName: string,
  payload: DeviceBridgeUpdate,
): Promise<FleetDevice> {
  const { data } = await api.patch<FleetDevice>(`/devices/${encodeURIComponent(deviceName)}`, {
    ip_address: payload.ip_address.trim(),
    port: payload.port,
    timezone: payload.timezone.trim(),
  });
  return data;
}
