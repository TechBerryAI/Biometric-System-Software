/** App-wide display locale (DD/MM/YYYY). */
const DISPLAY_LOCALE = "en-GB";

function parseISODate(isoDate: string): Date {
  return new Date(`${isoDate}T12:00:00`);
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

/** ISO datetime → DD/MM/YYYY, H:MM:SS */
export function fmtDisplayDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
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
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

/** Long timestamp for PDF headers and generated-at lines */
export function fmtGeneratedTimestamp(date: Date = new Date()): string {
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
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

export function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function formatISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

/** Last `count` calendar days ending today, oldest first (for charts). */
export function trailingDayISOs(count: number): string[] {
  const out: string[] = [];
  const end = new Date();
  for (let i = count - 1; i >= 0; i--) {
    out.push(formatISO(addDays(end, -i)));
  }
  return out;
}

export function dateList(fromISO: string, toISO: string): string[] {
  const out: string[] = [];
  let cur = new Date(`${fromISO}T12:00:00`);
  const end = new Date(`${toISO}T12:00:00`);
  while (cur <= end) {
    out.push(formatISO(cur));
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
    const start = addDays(d, -6);
    const from = formatISO(start);
    return {
      from,
      to: baseDateISO,
      label: `Last 7 days (${fmtDisplayDate(from)} → ${fmtDisplayDate(baseDateISO)})`,
    };
  }
  const start = addDays(d, -29);
  const from = formatISO(start);
  return {
    from,
    to: baseDateISO,
    label: `Last 30 days (${fmtDisplayDate(from)} → ${fmtDisplayDate(baseDateISO)})`,
  };
}
