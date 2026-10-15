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
  configureApiAuth(data.access_token ?? null);
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

export const RETIRED_PRIMARY_IP = "192.168.1.119";
export const RETIRED_PRIMARY_SERIAL = "JJA1240500503";

export type DeviceInspectSnapshot = {
  connected: boolean;
  connection_detail: string | null;
  firmware_version: string | null;
  serial_number: string | null;
  platform: string | null;
  fp_version: string | null;
  face_version: string | null;
  users: Array<{
    uid: number;
    user_id: string;
    name: string;
    privilege: number | null;
    group_id: string | null;
    card: string | null;
  }>;
  user_count: number;
  unsupported: string[];
  errors: Record<string, string>;
  inspected_at?: string;
  replacement_confirmed?: boolean;
  replacement_blocker?: string | null;
};

export type MigrationItem = {
  employee_id: number;
  employee_uuid: string;
  device_user_id: string;
  name: string;
  uid: number | null;
  card: string | null;
  action: string;
  planned_action?: string;
  conflict: string | null;
  status: string;
  command_uuid: string | null;
  last_error: string | null;
};

export type MigrationRecord = {
  migration_id: string;
  device_id: string;
  status: string;
  include_departed: boolean;
  target_ip: string;
  target_port: number;
  preflight_summary: {
    total_employees_in_scope: number;
    valid_for_migration: number;
    create: number;
    skip: number;
    update: number;
    conflict: number;
    missing_device_user_id: number;
    duplicate_user_id: number;
    duplicate_card: number;
    conflict_with_new_device: number;
    device_user_count: number;
    replacement_confirmed: boolean;
  } | null;
  report: {
    totals?: {
      items: number;
      create_success: number;
      update_success: number;
      skipped: number;
      conflicts: number;
      failed: number;
    };
    failed_user_ids?: string[];
    conflict_user_ids?: string[];
  } | null;
  last_error: string | null;
  items?: MigrationItem[];
  fingerprint_next_step: string;
};

const CUTOVER_TIMEOUT_MS = 600_000;

export async function inspectReplacementDevice(deviceName: string): Promise<DeviceInspectSnapshot> {
  const { data } = await api.post<DeviceInspectSnapshot>(
    `/devices/${encodeURIComponent(deviceName)}/inspect`,
    null,
    { timeout: CUTOVER_TIMEOUT_MS },
  );
  return data;
}

export async function preflightDeviceMigration(
  deviceName: string,
  includeDeparted = false,
): Promise<MigrationRecord> {
  const { data } = await api.post<MigrationRecord>(
    `/devices/${encodeURIComponent(deviceName)}/migration/preflight`,
    { include_departed: includeDeparted },
  );
  return data;
}

export async function dryRunDeviceMigration(
  deviceName: string,
  includeDeparted = false,
  migrationId?: string,
): Promise<MigrationRecord> {
  const { data } = await api.post<MigrationRecord>(
    `/devices/${encodeURIComponent(deviceName)}/migration/dry-run`,
    { include_departed: includeDeparted, migration_id: migrationId ?? null },
  );
  return data;
}

export async function executeDeviceMigration(
  deviceName: string,
  payload: {
    dry_run_id: string;
    confirm_target_device_name: string;
    confirm_target_ip: string;
    approve_update_user_ids?: string[];
  },
): Promise<MigrationRecord> {
  const { data } = await api.post<MigrationRecord>(
    `/devices/${encodeURIComponent(deviceName)}/migration/execute`,
    payload,
    { timeout: CUTOVER_TIMEOUT_MS },
  );
  return data;
}

export async function retryFailedDeviceMigration(
  deviceName: string,
  migrationId: string,
  payload: { confirm_target_device_name: string; confirm_target_ip: string },
): Promise<MigrationRecord> {
  const { data } = await api.post<MigrationRecord>(
    `/devices/${encodeURIComponent(deviceName)}/migration/${encodeURIComponent(migrationId)}/retry-failed`,
    payload,
    { timeout: CUTOVER_TIMEOUT_MS },
  );
  return data;
}

export async function fetchDeviceMigrationReport(
  deviceName: string,
  migrationId: string,
): Promise<MigrationRecord> {
  const { data } = await api.get<MigrationRecord>(
    `/devices/${encodeURIComponent(deviceName)}/migration/${encodeURIComponent(migrationId)}/report`,
  );
  return data;
}
