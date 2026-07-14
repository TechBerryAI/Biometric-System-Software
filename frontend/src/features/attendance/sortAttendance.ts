import type { DailySummaryRow } from "@/types";

export type AttendanceSortMode = "early_first" | "late_first" | "name_asc" | "work_desc" | "work_asc";

export const ATTENDANCE_SORT_LABELS: Record<AttendanceSortMode, string> = {
  early_first: "Early first",
  late_first: "Late first",
  name_asc: "Name A–Z",
  work_desc: "Most hours",
  work_asc: "Least hours",
};

type SortableAttendance = Pick<
  DailySummaryRow,
  "employee_name" | "first_check_in" | "last_check_out" | "total_work_minutes"
>;

function punchTime(iso: string | null): number | null {
  return iso ? new Date(iso).getTime() : null;
}

function isAbsent(row: SortableAttendance): boolean {
  return row.first_check_in == null && row.last_check_out == null;
}

function comparePresent(a: SortableAttendance, b: SortableAttendance, mode: AttendanceSortMode): number {
  const byName = () => a.employee_name.localeCompare(b.employee_name);

  if (mode === "name_asc") return byName();

  if (mode === "work_desc" || mode === "work_asc") {
    const aWork = a.total_work_minutes ?? -1;
    const bWork = b.total_work_minutes ?? -1;
    const diff = mode === "work_desc" ? bWork - aWork : aWork - bWork;
    return diff !== 0 ? diff : byName();
  }

  const aIn = punchTime(a.first_check_in);
  const bIn = punchTime(b.first_check_in);
  if (aIn != null && bIn != null) {
    const diff = mode === "late_first" ? bIn - aIn : aIn - bIn;
    return diff !== 0 ? diff : byName();
  }
  if (aIn != null) return -1;
  if (bIn != null) return 1;

  const aOut = punchTime(a.last_check_out);
  const bOut = punchTime(b.last_check_out);
  if (aOut != null && bOut != null) {
    const diff = mode === "late_first" ? bOut - aOut : aOut - bOut;
    return diff !== 0 ? diff : byName();
  }
  if (aOut != null) return -1;
  if (bOut != null) return 1;

  return byName();
}

/** Sort present rows by mode; absents always last (A–Z among themselves). */
export function sortAttendanceRows<T extends SortableAttendance>(
  rows: T[],
  mode: AttendanceSortMode
): T[] {
  const present = rows.filter((r) => !isAbsent(r));
  const absent = rows.filter((r) => isAbsent(r));

  present.sort((a, b) => comparePresent(a, b, mode));
  absent.sort((a, b) => a.employee_name.localeCompare(b.employee_name));

  return [...present, ...absent];
}
