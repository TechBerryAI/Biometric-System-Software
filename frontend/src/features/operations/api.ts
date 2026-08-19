import { api, SYNC_HTTP_TIMEOUT_MS } from "@/shared/api/client";

export type DeviceSyncResponse = {
  users_on_device: number;
  new_employees: number;
  attendance_records_fetched: number;
  new_attendance_logs: number;
  placeholder_employees_created?: number;
  skipped_reason?: string | null;
  skipped_corrected_punches?: number;
  punches_missing_after_insert?: number;
};

type DeviceSyncQueued = {
  accepted: boolean;
  task_id: string;
  status?: string;
};

type DeviceSyncJobStatus = {
  task_id: string;
  state: string;
  result: (DeviceSyncResponse & { ok?: boolean; error?: string; status_code?: number }) | null;
  error: string | null;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function waitForManualSyncJob(taskId: string): Promise<DeviceSyncResponse> {
  const started = Date.now();
  const deadline = started + SYNC_HTTP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const { data } = await api.get<DeviceSyncJobStatus>(`/sync/jobs/${encodeURIComponent(taskId)}`, {
      timeout: 15_000,
    });
    const failed = data.state === "FAILURE" || data.result?.ok === false;
    if (failed) {
      throw new Error(data.error || data.result?.error || "Sync failed");
    }
    if (data.state === "SUCCESS" && data.result) {
      return data.result;
    }
    if (data.state === "PENDING" && Date.now() - started > 45_000) {
      throw new Error(
        "Sync is queued but the worker has not picked it up. On the VM, confirm Celery is running (make start-vm / START_CELERY=1)."
      );
    }
    await sleep(2000);
  }
  throw new Error("Sync is still running on the server. Wait a minute, then refresh to see new punches.");
}

/** Pull all users + attendance still on the terminal (full history, read-only). */
export async function syncFromDevice(): Promise<DeviceSyncResponse> {
  const { data, status } = await api.post<DeviceSyncResponse | DeviceSyncQueued>("/sync/device", null, {
    timeout: SYNC_HTTP_TIMEOUT_MS,
    params: { full: true, wait: false },
    validateStatus: (code) => code === 200 || code === 202,
  });
  if (status === 202 && data && "task_id" in data && data.task_id) {
    return waitForManualSyncJob(data.task_id);
  }
  return data as DeviceSyncResponse;
}

export type IncompleteAttendanceSample = {
  employee_code: string;
  local_date: string;
  punch_count: number;
  first_punch: string | null;
  last_punch: string | null;
};

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
  incomplete_attendance_days?: number;
  last_attendance_sync_at?: string | null;
  incomplete_attendance_samples?: IncompleteAttendanceSample[];
  attendance_sync_stale?: boolean;
  device_connectivity_mode?: string;
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
