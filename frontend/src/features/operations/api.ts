import { api, SYNC_HTTP_TIMEOUT_MS } from "@/shared/api/client";

export type DeviceSyncResponse = {
  users_on_device: number;
  new_employees: number;
  attendance_records_fetched: number;
  new_attendance_logs: number;
  placeholder_employees_created?: number;
};

/** Pull users + attendance from the terminal (read-only), then reload DB-backed views. */
export async function syncFromDevice(full = false): Promise<DeviceSyncResponse> {
  const { data } = await api.post<DeviceSyncResponse>("/sync/device", null, {
    timeout: SYNC_HTTP_TIMEOUT_MS,
    params: full ? { full: true } : {},
  });
  return data;
}

export type OperationalMetrics = {
  queue_depth: number;
  stale_commands: number;
  dead_letter_commands: number;
  failing_devices: number;
  sync_drift_events: number;
  device_health_status?: string;
  device_ip?: string;
  device_port?: number;
  device_auto_sync_enabled?: boolean;
};

export type DeviceCommandRow = {
  command_uuid: string;
  device_id: string;
  command_type: string;
  status: string;
  retries: number;
  last_error: string | null;
  correlation_id: string | null;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export async function fetchOperationalMetrics(): Promise<OperationalMetrics> {
  const { data } = await api.get<OperationalMetrics>("/ops/metrics");
  return data;
}

export async function fetchDeviceCommands(status?: string): Promise<DeviceCommandRow[]> {
  const { data } = await api.get<DeviceCommandRow[]>("/ops/device-commands", {
    params: status ? { status } : {},
  });
  return data;
}
