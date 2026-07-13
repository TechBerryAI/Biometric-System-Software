import type { DailySummaryRow, EmployeeDailyAttendance, EmployeeDetail } from "@/types";

export type ReportFormat = "pdf" | "word" | "excel";

export type EmployeeReportPayload = {
  employee: EmployeeDetail;
  rows: EmployeeDailyAttendance[];
  fromDate: string;
  toDate: string;
};

export type AttendanceSummaryPayload = {
  periodLabel: string;
  rows: Array<DailySummaryRow & { summary_date: string }>;
};

export type DashboardKpiExport = {
  title: string;
  value: string;
  trend: string;
  comparison: string;
  insight: string;
};

export type DashboardDeptRow = {
  department: string;
  rank: number;
  attendance: number;
  punctuality: number;
  avgHours: number;
  overtimePct: number;
  absenteeRisk: number;
  productivity: number;
};

export type DashboardRadarRow = {
  metric: string;
  score: number;
};

export type DashboardReportPayload = {
  mode: string;
  dateRange: string;
  kpis: DashboardKpiExport[];
  deptMatrix: DashboardDeptRow[];
  radar: DashboardRadarRow[];
};
