import { api } from "@/shared/api/client";

export type HeatmapCell = {
  day: string;
  hour: number;
  punch_count: number;
};

export type AttendanceHeatmap = {
  period_start: string;
  period_end: string;
  generated_at: string;
  cells: HeatmapCell[];
};

export type BranchComparisonRow = {
  branch_id: string;
  branch_name: string;
  headcount: number;
  present_rate: number;
  late_rate: number;
  avg_work_hours: number;
};

export type BranchComparison = {
  period_start: string;
  period_end: string;
  generated_at: string;
  branches: BranchComparisonRow[];
};

export type DeviceUptimeRow = {
  device_uuid: string;
  device_name: string;
  uptime_percent: number;
  last_seen: string | null;
  health_status: string;
};

export type DeviceUptimeReport = {
  period_start: string;
  period_end: string;
  generated_at: string;
  devices: DeviceUptimeRow[];
};

export async function fetchAttendanceHeatmap(days = 7): Promise<AttendanceHeatmap> {
  const { data } = await api.get<AttendanceHeatmap>("/reporting/heatmap", { params: { days } });
  return data;
}

export async function fetchBranchComparison(days = 14): Promise<BranchComparison> {
  const { data } = await api.get<BranchComparison>("/reporting/branch-comparison", { params: { days } });
  return data;
}

export async function fetchDeviceUptime(days = 7): Promise<DeviceUptimeReport> {
  const { data } = await api.get<DeviceUptimeReport>("/reporting/device-uptime", { params: { days } });
  return data;
}
