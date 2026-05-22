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
    return { from: baseDateISO, to: baseDateISO, label: `Day ${baseDateISO}` };
  }
  if (period === "week") {
    const start = addDays(d, -6);
    const from = formatISO(start);
    return {
      from,
      to: baseDateISO,
      label: `Last 7 days (${from} → ${baseDateISO})`,
    };
  }
  const start = addDays(d, -29);
  const from = formatISO(start);
  return {
    from,
    to: baseDateISO,
    label: `Last 30 days (${from} → ${baseDateISO})`,
  };
}
