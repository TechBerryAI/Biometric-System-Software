/** App-wide display locale (DD/MM/YYYY). */
const DISPLAY_LOCALE = "en-GB";

/** Device/Settings timezone. Browser local time is never the attendance calendar. */
export const DEFAULT_APP_TIMEZONE = "Asia/Kolkata";

let appTimezone = DEFAULT_APP_TIMEZONE;

export function setAppTimezone(timezone: string | null | undefined): void {
  const value = (timezone || "").trim();
  appTimezone = value || DEFAULT_APP_TIMEZONE;
}

export function getAppTimezone(): string {
  return appTimezone;
}

type ZonedParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

function zonedDateParts(d: Date, timeZone = getAppTimezone()): ZonedParts {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(d);
  const num = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return {
    year: num("year"),
    month: num("month"),
    day: num("day"),
    hour: num("hour") % 24,
    minute: num("minute"),
    second: num("second"),
  };
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function parseISODate(isoDate: string): Date {
  return new Date(`${isoDate}T12:00:00`);
}

/** Calendar Y-M-D of a Date constructed from an ISO date + noon (date arithmetic). */
function localCalendarISO(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/** ISO date (YYYY-MM-DD) → DD/MM/YYYY */
export function fmtDisplayDate(isoDate: string): string {
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parseISODate(isoDate));
}

/** ISO date (YYYY-MM-DD) → weekday name, e.g. "Wednesday" */
export function fmtDayOfWeek(isoDate: string): string {
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
    weekday: "long",
  }).format(parseISODate(isoDate));
}

/** ISO datetime → DD/MM/YYYY, H:MM:SS in the app timezone */
export function fmtDisplayDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
    timeZone: getAppTimezone(),
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

/** Compact datetime for activity feeds: DD Mon, HH:MM */
export function fmtDisplayDateTimeShort(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
    timeZone: getAppTimezone(),
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

/** Long timestamp for PDF headers and generated-at lines */
export function fmtGeneratedTimestamp(date: Date = new Date()): string {
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
    timeZone: getAppTimezone(),
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/** Short chart axis label: DD/MM */
export function fmtChartDayLabel(isoDate: string): string {
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
    day: "numeric",
    month: "numeric",
  }).format(parseISODate(isoDate));
}

/** Ensure from <= to; swaps bounds when the user picks an inverted range. */
export function clampDateRange(fromISO: string, toISO: string): { from: string; to: string } {
  if (fromISO <= toISO) return { from: fromISO, to: toISO };
  return { from: toISO, to: fromISO };
}

export function formatISO(d: Date, timeZone = getAppTimezone()): string {
  const p = zonedDateParts(d, timeZone);
  return `${p.year}-${pad2(p.month)}-${pad2(p.day)}`;
}

export function todayISO(timeZone = getAppTimezone()): string {
  return formatISO(new Date(), timeZone);
}

export function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

/** Last `count` calendar days ending today in the app timezone, oldest first. */
export function trailingDayISOs(count: number): string[] {
  const out: string[] = [];
  const now = Date.now();
  for (let i = count - 1; i >= 0; i--) {
    out.push(formatISO(new Date(now - i * 86_400_000)));
  }
  return out;
}

export function dateList(fromISO: string, toISO: string): string[] {
  const out: string[] = [];
  let cur = new Date(`${fromISO}T12:00:00`);
  const end = new Date(`${toISO}T12:00:00`);
  while (cur <= end) {
    out.push(localCalendarISO(cur));
    cur = addDays(cur, 1);
  }
  return out;
}

export type ExportPeriod = "day" | "week" | "month";

export function getExportRange(
  baseDateISO: string,
  period: ExportPeriod
): { from: string; to: string; label: string } {
  const d = new Date(`${baseDateISO}T12:00:00`);
  if (period === "day") {
    return { from: baseDateISO, to: baseDateISO, label: `Day ${fmtDisplayDate(baseDateISO)}` };
  }
  if (period === "week") {
    const from = localCalendarISO(addDays(d, -6));
    return {
      from,
      to: baseDateISO,
      label: `Last 7 days (${fmtDisplayDate(from)} → ${fmtDisplayDate(baseDateISO)})`,
    };
  }
  const from = localCalendarISO(addDays(d, -29));
  return {
    from,
    to: baseDateISO,
    label: `Last 30 days (${fmtDisplayDate(from)} → ${fmtDisplayDate(baseDateISO)})`,
  };
}

export type TimeParts = { hour: number; minute: number; second: number };

export function isoToTimeParts(iso: string | null | undefined, timeZone = getAppTimezone()): TimeParts | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const p = zonedDateParts(d, timeZone);
  return { hour: p.hour, minute: p.minute, second: p.second };
}

/** Instant whose wall clock in `timeZone` equals `localDate` + `parts`. */
export function zonedWallClockToISO(
  localDate: string,
  parts: TimeParts,
  timeZone = getAppTimezone()
): string {
  const desired = `${localDate}T${pad2(parts.hour)}:${pad2(parts.minute)}:${pad2(parts.second)}`;
  let utc = Date.parse(`${desired}Z`);
  for (let i = 0; i < 4; i++) {
    const shown = zonedDateParts(new Date(utc), timeZone);
    const shownStamp = `${shown.year}-${pad2(shown.month)}-${pad2(shown.day)}T${pad2(shown.hour)}:${pad2(shown.minute)}:${pad2(shown.second)}`;
    const delta = Date.parse(`${desired}Z`) - Date.parse(`${shownStamp}Z`);
    utc += delta;
    if (delta === 0) break;
  }
  return new Date(utc).toISOString();
}
