import { describe, expect, it } from "vitest";
import { sortAttendanceRows } from "@/features/attendance/sortAttendance";

const rows = [
  {
    employee_name: "Ada Lovelace",
    first_check_in: "2024-06-01T08:00:00Z",
    last_check_out: "2024-06-01T17:00:00Z",
    total_work_minutes: 480,
  },
  {
    employee_name: "Grace Hopper",
    first_check_in: "2024-06-01T10:00:00Z",
    last_check_out: "2024-06-01T18:00:00Z",
    total_work_minutes: 420,
  },
  {
    employee_name: "Zoe Absent",
    first_check_in: null,
    last_check_out: null,
    total_work_minutes: null,
  },
];

describe("sortAttendanceRows", () => {
  it("orders late first and pins absents last", () => {
    const sorted = sortAttendanceRows(rows, "late_first");
    expect(sorted.map((r) => r.employee_name)).toEqual(["Grace Hopper", "Ada Lovelace", "Zoe Absent"]);
  });

  it("orders alphabetically with absents last", () => {
    const sorted = sortAttendanceRows(rows, "name_asc");
    expect(sorted.map((r) => r.employee_name)).toEqual(["Ada Lovelace", "Grace Hopper", "Zoe Absent"]);
  });
});
