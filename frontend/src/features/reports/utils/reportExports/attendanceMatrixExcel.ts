import ExcelJS from "exceljs";
import { dateList, isoToTimeParts } from "@/lib/dates";
import type { AttendanceSummaryPayload } from "./types";
import { triggerBlobDownload } from "./shared";

/**
 * All-employee attendance grid: one sheet per calendar month, one row per
 * employee. Every date spans three columns — In, Out, Hours — under a merged
 * date header. Days without a punch merge those three cells into one label:
 * "Saturday" / "Sunday" on weekends, "Absent" otherwise. Each month sheet ends
 * with per-employee totals (present days, absent days, total hours); exports
 * spanning several months also get a leading "Summary" sheet for the whole range.
 */

const FIXED_COLS = 2; // Employee, Device ID
const DAY_COLS = 3; // In, Out, Hours
const DAY_SUBHEADERS = ["In", "Out", "Hours"];
const TOTAL_HEADERS = ["Present Days", "Absent Days", "Total Hours"];
const HEADER_ROWS = 2;

const TIME_FMT = "h:mm";
/** Elapsed-time format so totals above 24h don't wrap around. */
const DURATION_FMT = "[h]:mm";

const thinBorder: Partial<ExcelJS.Borders> = {
  top: { style: "thin", color: { argb: "FF000000" } },
  left: { style: "thin", color: { argb: "FF000000" } },
  bottom: { style: "thin", color: { argb: "FF000000" } },
  right: { style: "thin", color: { argb: "FF000000" } },
};

const HEADER_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFD9E1F2" } };
const TOTAL_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFFFF2CC" } };
const WEEKEND_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFEDEDED" } };
const ABSENT_FILL: ExcelJS.Fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFFCE4E4" } };

const WEEKEND_LABELS: Record<number, string> = { 0: "Sunday", 6: "Saturday" };

type MatrixEmployee = { id: number; name: string; deviceUserId: string };

type DayRecord = {
  checkIn: string | null;
  checkOut: string | null;
  workMinutes: number | null;
};

type EmployeeTotals = { present: number; absent: number; minutes: number };

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

function excelDuration(minutes: number): number {
  return minutes / (24 * 60);
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

function hasPunch(day: DayRecord | undefined): day is DayRecord {
  return !!day && (day.checkIn != null || day.checkOut != null);
}

function computeTotals(
  employee: MatrixEmployee,
  dates: string[],
  days: Map<string, DayRecord>
): EmployeeTotals {
  const totals: EmployeeTotals = { present: 0, absent: 0, minutes: 0 };
  for (const isoDate of dates) {
    const day = days.get(`${employee.id}|${isoDate}`);
    if (hasPunch(day)) {
      totals.present += 1;
      totals.minutes += day.workMinutes ?? 0;
    } else if (!weekendLabel(isoDate)) {
      totals.absent += 1;
    }
  }
  return totals;
}

function styleHeaderCell(cell: ExcelJS.Cell, fill: ExcelJS.Fill = HEADER_FILL): void {
  cell.font = { bold: true, name: "Calibri", size: 11 };
  cell.alignment = { horizontal: "center", vertical: "middle", wrapText: true };
  cell.border = thinBorder;
  cell.fill = fill;
}

function styleBodyCell(cell: ExcelJS.Cell): void {
  cell.font = { ...(cell.font ?? {}), name: "Calibri", size: 11 };
  cell.alignment = { horizontal: "center", vertical: "middle" };
  cell.border = thinBorder;
}

function writeTotalsCells(row: ExcelJS.Row, firstCol: number, totals: EmployeeTotals): void {
  row.getCell(firstCol).value = totals.present;
  row.getCell(firstCol + 1).value = totals.absent;
  const hours = row.getCell(firstCol + 2);
  hours.value = excelDuration(totals.minutes);
  hours.numFmt = DURATION_FMT;
  for (let i = 0; i < TOTAL_HEADERS.length; i++) {
    const cell = row.getCell(firstCol + i);
    styleBodyCell(cell);
    cell.font = { bold: true, name: "Calibri", size: 11 };
    cell.fill = TOTAL_FILL;
  }
}

function writeDayCells(sheet: ExcelJS.Worksheet, rowNumber: number, firstCol: number, isoDate: string, day: DayRecord | undefined): void {
  const row = sheet.getRow(rowNumber);
  const inCell = row.getCell(firstCol);
  const outCell = row.getCell(firstCol + 1);
  const hoursCell = row.getCell(firstCol + 2);

  if (!hasPunch(day)) {
    const weekend = weekendLabel(isoDate);
    sheet.mergeCells(rowNumber, firstCol, rowNumber, firstCol + DAY_COLS - 1);
    inCell.value = weekend ?? "Absent";
    inCell.fill = weekend ? WEEKEND_FILL : ABSENT_FILL;
    if (!weekend) inCell.font = { color: { argb: "FFC00000" } };
    styleBodyCell(inCell);
    return;
  }

  const inTime = excelTime(day.checkIn);
  const outTime = excelTime(day.checkOut);
  if (inTime != null) {
    inCell.value = inTime;
    inCell.numFmt = TIME_FMT;
  } else {
    inCell.value = "Missing";
  }
  if (outTime != null) {
    outCell.value = outTime;
    outCell.numFmt = TIME_FMT;
  } else {
    outCell.value = "Missing";
  }
  if (day.workMinutes != null) {
    hoursCell.value = excelDuration(day.workMinutes);
    hoursCell.numFmt = DURATION_FMT;
  } else {
    hoursCell.value = "—";
  }
  for (const cell of [inCell, outCell, hoursCell]) styleBodyCell(cell);
}

function writeMonthSheet(
  workbook: ExcelJS.Workbook,
  sheetName: string,
  dates: string[],
  employees: MatrixEmployee[],
  days: Map<string, DayRecord>
): void {
  const sheet = workbook.addWorksheet(sheetName, {
    views: [{ state: "frozen", xSplit: FIXED_COLS, ySplit: HEADER_ROWS }],
  });
  const dayCol = (i: number) => FIXED_COLS + i * DAY_COLS + 1;
  const totalsCol = dayCol(dates.length);

  sheet.getColumn(1).width = 34;
  sheet.getColumn(2).width = 12;
  for (let col = FIXED_COLS + 1; col < totalsCol; col++) sheet.getColumn(col).width = 8;
  for (let i = 0; i < TOTAL_HEADERS.length; i++) sheet.getColumn(totalsCol + i).width = 12;

  // Header rows: fixed columns and the totals block span both rows' worth of labels.
  const top = sheet.getRow(1);
  const sub = sheet.getRow(2);
  sheet.mergeCells(1, 1, 2, 1);
  sheet.mergeCells(1, 2, 2, 2);
  top.getCell(1).value = "Employee";
  top.getCell(2).value = "Device ID";
  styleHeaderCell(top.getCell(1));
  styleHeaderCell(top.getCell(2));

  dates.forEach((isoDate, i) => {
    const col = dayCol(i);
    sheet.mergeCells(1, col, 1, col + DAY_COLS - 1);
    const dateCell = top.getCell(col);
    dateCell.value = excelDate(isoDate);
    dateCell.numFmt = "ddd dd-mmm-yy";
    styleHeaderCell(dateCell, weekendLabel(isoDate) ? WEEKEND_FILL : HEADER_FILL);
    DAY_SUBHEADERS.forEach((label, j) => {
      const cell = sub.getCell(col + j);
      cell.value = label;
      styleHeaderCell(cell);
    });
  });

  sheet.mergeCells(1, totalsCol, 1, totalsCol + TOTAL_HEADERS.length - 1);
  top.getCell(totalsCol).value = "Month Total";
  styleHeaderCell(top.getCell(totalsCol), TOTAL_FILL);
  TOTAL_HEADERS.forEach((label, j) => {
    const cell = sub.getCell(totalsCol + j);
    cell.value = label;
    styleHeaderCell(cell, TOTAL_FILL);
  });

  employees.forEach((employee, rowIndex) => {
    const rowNumber = rowIndex + HEADER_ROWS + 1;
    const row = sheet.getRow(rowNumber);
    row.getCell(1).value = employee.name;
    row.getCell(2).value = employee.deviceUserId;
    styleBodyCell(row.getCell(1));
    styleBodyCell(row.getCell(2));
    row.getCell(1).alignment = { horizontal: "left", vertical: "middle" };

    dates.forEach((isoDate, i) => {
      writeDayCells(sheet, rowNumber, dayCol(i), isoDate, days.get(`${employee.id}|${isoDate}`));
    });
    writeTotalsCells(row, totalsCol, computeTotals(employee, dates, days));
  });
}

function writeSummarySheet(
  workbook: ExcelJS.Workbook,
  range: { from: string; to: string },
  dates: string[],
  employees: MatrixEmployee[],
  days: Map<string, DayRecord>
): void {
  const sheet = workbook.addWorksheet("Summary", {
    views: [{ state: "frozen", xSplit: FIXED_COLS, ySplit: 1 }],
  });
  const headers = ["Employee", "Device ID", ...TOTAL_HEADERS, "Avg Hours / Present Day"];
  [34, 12, 12, 12, 12, 14].forEach((w, i) => (sheet.getColumn(i + 1).width = w));

  const header = sheet.getRow(1);
  headers.forEach((label, i) => {
    header.getCell(i + 1).value = label;
    styleHeaderCell(header.getCell(i + 1));
  });

  employees.forEach((employee, rowIndex) => {
    const row = sheet.getRow(rowIndex + 2);
    row.getCell(1).value = employee.name;
    row.getCell(2).value = employee.deviceUserId;
    styleBodyCell(row.getCell(1));
    styleBodyCell(row.getCell(2));
    row.getCell(1).alignment = { horizontal: "left", vertical: "middle" };

    const totals = computeTotals(employee, dates, days);
    writeTotalsCells(row, FIXED_COLS + 1, totals);
    const avg = row.getCell(FIXED_COLS + TOTAL_HEADERS.length + 1);
    avg.value = totals.present > 0 ? excelDuration(Math.round(totals.minutes / totals.present)) : "—";
    if (totals.present > 0) avg.numFmt = DURATION_FMT;
    styleBodyCell(avg);
  });

  const note = sheet.getRow(employees.length + 3).getCell(1);
  note.value = `Period: ${range.from} to ${range.to}`;
  note.font = { italic: true, name: "Calibri", size: 10 };
}

export async function downloadAttendanceMatrixExcel(args: AttendanceSummaryPayload): Promise<void> {
  const range = resolveRange(args);
  if (!range) throw new Error("No attendance data to export for this period.");

  const employeesById = new Map<number, MatrixEmployee>();
  const days = new Map<string, DayRecord>();
  for (const r of args.rows) {
    if (!employeesById.has(r.employee_id)) {
      employeesById.set(r.employee_id, {
        id: r.employee_id,
        name: r.employee_name,
        deviceUserId: r.device_user_id,
      });
    }
    days.set(`${r.employee_id}|${r.summary_date}`, {
      checkIn: r.first_check_in,
      checkOut: r.last_check_out,
      workMinutes: r.total_work_minutes,
    });
  }
  const employees = Array.from(employeesById.values()).sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
  );

  const workbook = new ExcelJS.Workbook();
  workbook.creator = "Biometric Attendance";
  workbook.created = new Date();

  const allDates = dateList(range.from, range.to);
  const months = groupByMonth(allDates);
  if (months.size > 1) writeSummarySheet(workbook, range, allDates, employees, days);
  for (const [monthKey, dates] of months) {
    writeMonthSheet(workbook, monthSheetName(monthKey), dates, employees, days);
  }

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  triggerBlobDownload(blob, `attendance_summary_${range.from}_${range.to}.xlsx`);
}
