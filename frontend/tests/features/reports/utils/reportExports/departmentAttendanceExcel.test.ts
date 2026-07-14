import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  downloadDepartmentAttendanceExcel,
  fmtAttendanceInstruction,
  fmtMonthSpan,
  fmtPunchAmPm,
  fmtReportDate,
  fmtTotalHours,
  resolveAttendanceMark,
} from "@/features/reports/utils/reportExports/departmentAttendanceExcel";
import type { Employee } from "@/types";

vi.mock("@/features/reports/utils/reportExports/shared", async () => {
  const actual = await vi.importActual<typeof import("@/features/reports/utils/reportExports/shared")>(
    "@/features/reports/utils/reportExports/shared"
  );
  return {
    ...actual,
    triggerBlobDownload: vi.fn(),
  };
});

describe("departmentAttendanceExcel helpers", () => {
  it("formats report dates as DD-MMM-YY", () => {
    expect(fmtReportDate("2026-05-26")).toBe("26-May-26");
    expect(fmtReportDate("2026-06-01")).toBe("01-Jun-26");
  });

  it("formats month span and instruction line", () => {
    expect(fmtMonthSpan("2026-05-26", "2026-06-25")).toBe("May - June");
    expect(fmtMonthSpan("2026-05-01", "2026-05-31")).toBe("May");
    expect(fmtAttendanceInstruction("2026-05-26", "2026-06-25")).toBe(
      "Mark the Attendance from 26th May to 25th June 2026"
    );
  });

  it("formats punch times and hours", () => {
    expect(fmtPunchAmPm("2026-05-26T04:00:00.000Z")).toMatch(/9:30am/i);
    expect(fmtTotalHours(540)).toBe("9");
    expect(fmtTotalHours(570)).toBe("9.5");
    expect(fmtTotalHours(null)).toBe("");
  });

  it("resolves Present / Week Off / Leave", () => {
    expect(
      resolveAttendanceMark("2026-05-26", {
        summary_date: "2026-05-26",
        employee_id: 1,
        device_user_id: "TBI1",
        employee_name: "Ada",
        first_check_in: "2026-05-26T04:00:00.000Z",
        last_check_out: "2026-05-26T13:00:00.000Z",
        total_work_minutes: 540,
        sessions_count: 1,
      })
    ).toBe("Present");
    // 2026-05-30 is Saturday
    expect(resolveAttendanceMark("2026-05-30", null)).toBe("Week Off");
    // 2026-06-01 is Monday
    expect(resolveAttendanceMark("2026-06-01", null)).toBe("Leave");
  });
});

describe("downloadDepartmentAttendanceExcel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("builds a multi-sheet workbook and triggers download", async () => {
    const { triggerBlobDownload } = await import("@/features/reports/utils/reportExports/shared");
    const employee: Employee = {
      id: 1,
      device_user_id: "TBI001",
      name: "Abhishek Chettiar",
      department: "AI Department",
      shift_start: null,
      shift_end: null,
      created_at: "2026-01-01T00:00:00Z",
    };

    await downloadDepartmentAttendanceExcel({
      department: "AI Department",
      fromDate: "2026-05-26",
      toDate: "2026-05-27",
      members: [
        {
          employee,
          days: [
            {
              isoDate: "2026-05-26",
              summary: {
                summary_date: "2026-05-26",
                employee_id: 1,
                device_user_id: "TBI001",
                employee_name: "Abhishek Chettiar",
                first_check_in: "2026-05-26T04:00:00.000Z",
                last_check_out: "2026-05-26T13:00:00.000Z",
                total_work_minutes: 540,
                sessions_count: 1,
              },
            },
            { isoDate: "2026-05-27", summary: null },
          ],
        },
      ],
    });

    expect(triggerBlobDownload).toHaveBeenCalledTimes(1);
    const [blob, filename] = vi.mocked(triggerBlobDownload).mock.calls[0];
    expect(blob).toBeInstanceOf(Blob);
    expect(filename).toContain("department_attendance_ai_department");
    expect(filename).toMatch(/\.xlsx$/);
  });

  it("rejects empty member lists", async () => {
    await expect(
      downloadDepartmentAttendanceExcel({
        department: "Empty Dept",
        fromDate: "2026-05-26",
        toDate: "2026-05-26",
        members: [],
      })
    ).rejects.toThrow(/No employees found/);
  });
});
