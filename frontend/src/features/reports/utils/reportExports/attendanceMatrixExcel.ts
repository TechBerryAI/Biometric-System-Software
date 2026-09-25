import ExcelJS from "exceljs";
import { dateList, isoToTimeParts } from "@/lib/dates";
import type { AttendanceSummaryPayload } from "./types";
import { triggerBlobDownload } from "./shared";

/**
 * All-employee attendance grid: one sheet per calendar month, one row per
 * employee, one column per date. Cells hold the first check-in time; weekend
 * days without a punch read "Saturday" / "Sunday"; other missing days read
 * "Absent".
 */

const FIXED_COLS = 2; // Employee, Device ID

const thinBorder: Partial<ExcelJS.Borders> = {
  top: { style: "thin", color: { argb: "FF000000" } },
  left: { style: "thin", color: { argb: "FF000000" } },
  bottom: { style: "thin", color: { argb: "FF000000" } },
  right: { style: "thin", color: { argb: "FF000000" } },
};

const WEEKEND_LABELS: Record<number, string> = { 0: "Sunday", 6: "Saturday" };

type MatrixEmployee = { id: number; name: string; deviceUserId: string };

function isoParts(isoDate: string): [number, number, number] {
  const [y, m, d] = isoDate.split("-").map(Number);
  return [y, m, d];
}

/** Date cell value that Excel shows as the same calendar day in any timezone. */
function excelDate(isoDate: string): Date {
  const [y, m, d] = isoParts(isoDate);
  return new Date(Date.UTC(y, m - 1, d));
}

function weekendLabel(isoDate: string): string | null {
  return WEEKEND_LABELS[excelDate(isoDate).getUTCDay()] ?? null;
}

/** Fraction of a day, Excel's native time representation (shown via h:mm). */
function excelTime(iso: string | null | undefined): number | null {
  const parts = isoToTimeParts(iso);
  if (!parts) return null;
  return (parts.hour * 60 + parts.minute) / (24 * 60);
}

function monthSheetName(monthKey: string): string {
  const [y, m] = isoParts(`${monthKey}-01`);
  const month = new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en-GB", {
    month: "long",
    timeZone: "UTC",
  });
  return `${month} ${y}`;
}

function groupByMonth(dates: string[]): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const d of dates) {
    const key = d.slice(0, 7);
    const list = out.get(key);
    if (list) list.push(d);
    else out.set(key, [d]);
  }
  return out;
}

function resolveRange(args: AttendanceSummaryPayload): { from: string; to: string } | null {
  if (args.fromDate && args.toDate) return { from: args.fromDate, to: args.toDate };
  const dates = args.rows.map((r) => r.summary_date).sort();
  if (dates.length === 0) return null;
  return { from: dates[0], to: dates[dates.length - 1] };
}

function writeMonthSheet(
  workbook: ExcelJS.Workbook,
  sheetName: string,
  dates: string[],
  employees: MatrixEmployee[],
  checkIns: Map<string, string | null>
): void {
  const sheet = workbook.addWorksheet(sheetName, {
    views: [{ state: "frozen", xSplit: FIXED_COLS, ySplit: 1 }],
  });

  sheet.getColumn(1).width = 34;
  sheet.getColumn(2).width = 12;
  dates.forEach((_, i) => {
    sheet.getColumn(FIXED_COLS + i + 1).width = 11;
  });

  const header = sheet.getRow(1);
  header.getCell(1).value = "Employee";
  header.getCell(2).value = "Device ID";
  dates.forEach((isoDate, i) => {
    const cell = header.getCell(FIXED_COLS + i + 1);
    cell.value = excelDate(isoDate);
    cell.numFmt = "dd-mmm-yy";
  });
  for (let col = 1; col <= FIXED_COLS + dates.length; col++) {
    const cell = header.getCell(col);
    cell.font = { bold: true, name: "Calibri", size: 11 };
    cell.alignment = { horizontal: "center", vertical: "middle" };
    cell.border = thinBorder;
  }

  employees.forEach((employee, rowIndex) => {
    const row = sheet.getRow(rowIndex + 2);
    row.getCell(1).value = employee.name;
    row.getCell(2).value = employee.deviceUserId;

    dates.forEach((isoDate, i) => {
      const cell = row.getCell(FIXED_COLS + i + 1);
      const time = excelTime(checkIns.get(`${employee.id}|${isoDate}`));
      if (time != null) {
        cell.value = time;
        cell.numFmt = "h:mm";
      } else {
        cell.value = weekendLabel(isoDate) ?? "Absent";
      }
      cell.alignment = { horizontal: "center", vertical: "middle" };
    });

    for (let col = 1; col <= FIXED_COLS + dates.length; col++) {
      const cell = row.getCell(col);
      cell.border = thinBorder;
      cell.font = { name: "Calibri", size: 11 };
    }
  });
}

export async function downloadAttendanceMatrixExcel(args: AttendanceSummaryPayload): Promise<void> {
  const range = resolveRange(args);
  if (!range) throw new Error("No attendance data to export for this period.");

  const employeesById = new Map<number, MatrixEmployee>();
  const checkIns = new Map<string, string | null>();
  for (const r of args.rows) {
    if (!employeesById.has(r.employee_id)) {
      employeesById.set(r.employee_id, {
        id: r.employee_id,
        name: r.employee_name,
        deviceUserId: r.device_user_id,
      });
    }
    checkIns.set(`${r.employee_id}|${r.summary_date}`, r.first_check_in);
  }
  const employees = Array.from(employeesById.values()).sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
  );

  const workbook = new ExcelJS.Workbook();
  workbook.creator = "Biometric Attendance";
  workbook.created = new Date();

  for (const [monthKey, dates] of groupByMonth(dateList(range.from, range.to))) {
    writeMonthSheet(workbook, monthSheetName(monthKey), dates, employees, checkIns);
  }

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  triggerBlobDownload(blob, `attendance_summary_${range.from}_${range.to}.xlsx`);
}
