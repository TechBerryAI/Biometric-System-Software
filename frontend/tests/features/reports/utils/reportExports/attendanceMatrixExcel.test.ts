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

function row(
  employee_id: number,
  name: string,
  summary_date: string,
  first_check_in: string | null,
  last_check_out: string | null = null,
  total_work_minutes: number | null = null
) {
  return {
    summary_date,
    employee_id,
    device_user_id: `TBC${employee_id}`,
    employee_name: name,
    first_check_in,
    last_check_out,
    total_work_minutes,
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

  it("shows in time, out time and hours for every date plus month totals", async () => {
    await downloadAttendanceMatrixExcel({
      periodLabel: "Custom range",
      fromDate: "2026-07-31",
      toDate: "2026-08-03",
      rows: [
        // 03:30Z = 09:00 IST, 12:45Z = 18:15 IST
        row(2, "Zara", "2026-07-31", "2026-07-31T03:30:00Z", "2026-07-31T12:45:00Z", 555),
        row(1, "Ada", "2026-08-03", "2026-08-03T04:15:00Z", null, null),
        row(1, "Ada", "2026-07-31", null),
      ],
    });

    const workbook = await readDownloadedWorkbook();
    // Range spans two months → leading Summary sheet.
    expect(workbook.worksheets.map((s) => s.name)).toEqual(["Summary", "July 2026", "August 2026"]);

    const july = workbook.getWorksheet("July 2026")!;
    expect(july.getRow(1).getCell(1).value).toBe("Employee");
    expect(july.getRow(1).getCell(2).value).toBe("Device ID");
    expect((july.getRow(1).getCell(3).value as Date).toISOString().slice(0, 10)).toBe("2026-07-31");
    expect([3, 4, 5].map((c) => july.getRow(2).getCell(c).value)).toEqual(["In", "Out", "Hours"]);
    expect(july.getRow(1).getCell(6).value).toBe("Month Total");
    expect([6, 7, 8].map((c) => july.getRow(2).getCell(c).value)).toEqual([
      "Present Days",
      "Absent Days",
      "Total Hours",
    ]);

    // Ada: absent on Fri 31 Jul, merged across In/Out/Hours.
    expect(july.getRow(3).getCell(1).value).toBe("Ada");
    expect(july.getRow(3).getCell(3).value).toBe("Absent");
    expect(july.getRow(3).getCell(5).isMerged).toBe(true);
    expect([6, 7].map((c) => july.getRow(3).getCell(c).value)).toEqual([0, 1]);

    // Zara: full day with in, out and hours.
    const zara = july.getRow(4);
    expect(zara.getCell(1).value).toBe("Zara");
    expect(zara.getCell(2).value).toBe("TBC2");
    expect(hhmm(zara.getCell(3).value)).toBe("09:00");
    expect(zara.getCell(3).numFmt).toBe("h:mm");
    expect(hhmm(zara.getCell(4).value)).toBe("18:15");
    expect(hhmm(zara.getCell(5).value)).toBe("09:15");
    expect(zara.getCell(5).numFmt).toBe("[h]:mm");
    expect([6, 7].map((c) => zara.getCell(c).value)).toEqual([1, 0]);
    expect(hhmm(zara.getCell(8).value)).toBe("09:15");

    const august = workbook.getWorksheet("August 2026")!;
    // 1 Aug 2026 = Saturday, 2 Aug = Sunday, 3 Aug = Monday
    expect(august.getRow(3).getCell(3).value).toBe("Saturday");
    expect(august.getRow(3).getCell(6).value).toBe("Sunday");
    expect(hhmm(august.getRow(3).getCell(9).value)).toBe("09:45");
    expect(august.getRow(3).getCell(10).value).toBe("Missing");
    expect(august.getRow(3).getCell(11).value).toBe("—");
    expect(august.getRow(4).getCell(9).value).toBe("Absent");

    const summary = workbook.getWorksheet("Summary")!;
    expect(summary.getRow(1).getCell(5).value).toBe("Total Hours");
    expect([3, 4].map((c) => summary.getRow(2).getCell(c).value)).toEqual([1, 1]); // Ada
    expect([3, 4].map((c) => summary.getRow(3).getCell(c).value)).toEqual([1, 1]); // Zara
    expect(hhmm(summary.getRow(3).getCell(5).value)).toBe("09:15");
  });

  it("skips the summary sheet for a single-month export", async () => {
    await downloadAttendanceMatrixExcel({
      periodLabel: "Day",
      fromDate: "2026-07-31",
      toDate: "2026-07-31",
      rows: [row(1, "Ada", "2026-07-31", "2026-07-31T03:30:00Z", "2026-07-31T11:30:00Z", 480)],
    });

    const workbook = await readDownloadedWorkbook();
    expect(workbook.worksheets.map((s) => s.name)).toEqual(["July 2026"]);
  });

  it("rejects an empty export without a window", async () => {
    await expect(downloadAttendanceMatrixExcel({ periodLabel: "x", rows: [] })).rejects.toThrow();
  });
});
