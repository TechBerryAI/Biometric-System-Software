import {
  sortAttendanceRows,
  type AttendanceSortMode,
} from "@/features/attendance/sortAttendance";
import type { DailySummaryRow } from "@/types";

export type SummaryRowWithDate = DailySummaryRow & { summary_date: string };

/**
 * Chronological dates; within each day apply Attendance sort independently.
 * Never ranks across the whole period.
 */
export function buildSortedSummaryRows(
  byDay: Record<string, DailySummaryRow[]>,
  dates: string[],
  mode: AttendanceSortMode,
): SummaryRowWithDate[] {
  const allRows: SummaryRowWithDate[] = [];
  for (const day of dates) {
    const sorted = sortAttendanceRows(byDay[day] ?? [], mode);
    for (const row of sorted) {
      allRows.push({ ...row, summary_date: day });
    }
  }
  return allRows;
}
