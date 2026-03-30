export interface Employee {
  id: number;
  device_user_id: string;
  device_uid?: number | null;
  device_privilege?: number | null;
  device_group_id?: string | null;
  device_card?: string | null;
  name: string;
  department: string | null;
  shift_start: string | null;
  shift_end: string | null;
  created_at: string;
}

export interface EmployeeDetail extends Employee {
  total_logs: number;
  first_punch_at: string | null;
  last_punch_at: string | null;
  total_attendance_days: number;
  total_complete_days: number;
}

export interface EmployeeDailyAttendance {
  summary_date: string;
  first_check_in: string | null;
  last_check_out: string | null;
  total_work_minutes: number | null;
  late_arrival: boolean;
  absent: boolean;
  punch_count: number;
}

export interface AttendanceLog {
  id: number;
  employee_code: string;
  timestamp: string;
  device_id: string;
  punch_type: string;
  created_at: string;
}

export interface AttendanceSession {
  id: number;
  employee_id: number;
  check_in: string;
  check_out: string | null;
  work_duration: number | null;
  late_minutes: number | null;
  early_minutes: number | null;
  status: string;
  created_at: string;
}

export interface DailySummaryRow {
  summary_date: string;
  employee_id: number;
  device_user_id: string;
  employee_name: string;
  first_check_in: string | null;
  last_check_out: string | null;
  total_work_minutes: number | null;
  late_arrival: boolean;
  sessions_count: number;
}
