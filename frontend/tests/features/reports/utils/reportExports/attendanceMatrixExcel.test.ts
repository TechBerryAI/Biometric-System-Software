import ExcelJS from "exceljs";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { downloadAttendanceMatrixExcel } from "@/features/reports/utils/reportExports/attendanceMatrixExcel";
import { triggerBlobDownload } from "@/features/reports/utils/reportExports/shared";

vi.mock("@/features/reports/utils/reportExports/shared", async () => {
  const actual = await vi.importActual<typeof import("@/features/reports/utils/reportExports/shared")>(
    "@/features/reports/utils/reportExports/shared"
  );
  return {
    ...actual,
    triggerBlobDownload: vi.fn(),
  };
});

function row(employee_id: number, name: string, summary_date: string, first_check_in: string | null) {
  return {
    summary_date,
    employee_id,
    device_user_id: `TBC${employee_id}`,
    employee_name: name,
    first_check_in,
    last_check_out: null,
    total_work_minutes: null,
    sessions_count: first_check_in ? 1 : 0,
  };
}

/** ExcelJS reads h:mm cells back as dates on the 1899-12-30 epoch. */
function hhmm(value: ExcelJS.CellValue): string {
  return (value as Date).toISOString().slice(11, 16);
}

async function readDownloadedWorkbook(): Promise<ExcelJS.Workbook> {
  const [blob, filename] = vi.mocked(triggerBlobDownload).mock.calls[0];
  expect(filename).toMatch(/\.xlsx$/);
  const workbook = new ExcelJS.Workbook();
  const buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob as Blob);
  });
  await workbook.xlsx.load(buffer);
  return workbook;
}

describe("FE-UNIT-XLS-001 attendance matrix excel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lays out employees as rows and dates as columns with check-in times", async () => {
    await downloadAttendanceMatrixExcel({
      periodLabel: "Custom range",
      fromDate: "2026-07-31",
      toDate: "2026-08-03",
      rows: [
        // 03:30Z = 09:00 IST
        row(2, "Zara", "2026-07-31", "2026-07-31T03:30:00Z"),
        row(1, "Ada", "2026-08-03", "2026-08-03T04:15:00Z"),
        row(1, "Ada", "2026-07-31", null),
      ],
    });

    const workbook = await readDownloadedWorkbook();
    expect(workbook.worksheets.map((s) => s.name)).toEqual(["July 2026", "August 2026"]);

    const july = workbook.getWorksheet("July 2026")!;
    expect(july.getRow(1).getCell(1).value).toBe("Employee");
    expect(july.getRow(1).getCell(2).value).toBe("Device ID");
    expect((july.getRow(1).getCell(3).value as Date).toISOString().slice(0, 10)).toBe("2026-07-31");
    expect(july.getRow(2).getCell(1).value).toBe("Ada");
    expect(july.getRow(2).getCell(3).value).toBe("Absent");
    expect(july.getRow(3).getCell(1).value).toBe("Zara");
    expect(july.getRow(3).getCell(2).value).toBe("TBC2");
    expect(hhmm(july.getRow(3).getCell(3).value)).toBe("09:00");
    expect(july.getRow(3).getCell(3).numFmt).toBe("h:mm");

    const august = workbook.getWorksheet("August 2026")!;
    // 1 Aug 2026 = Saturday, 2 Aug = Sunday, 3 Aug = Monday
    expect(august.getRow(2).getCell(3).value).toBe("Saturday");
    expect(august.getRow(2).getCell(4).value).toBe("Sunday");
    expect(hhmm(august.getRow(2).getCell(5).value)).toBe("09:45");
    expect(august.getRow(3).getCell(5).value).toBe("Absent");
  });

  it("rejects an empty export without a window", async () => {
    await expect(downloadAttendanceMatrixExcel({ periodLabel: "x", rows: [] })).rejects.toThrow();
  });
});
