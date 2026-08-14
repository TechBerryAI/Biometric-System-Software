import { saveAs } from "file-saver";

export function fmtMinutes(total: number | null): string {
  if (total == null) return "—";
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function safeFilename(value: string): string {
  return value.replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "").toLowerCase();
}

export function triggerBlobDownload(blob: Blob, filename: string): void {
  saveAs(blob, filename);
}

export function formatExtension(format: "pdf" | "word" | "excel"): string {
  if (format === "word") return "docx";
  if (format === "excel") return "xlsx";
  return "pdf";
}

/** Insert a blank row between day groups (dates must already be chronological). */
export function mapRowsWithDaySeparators<T extends { summary_date: string }>(
  rows: T[],
  mapRow: (row: T) => (string | number)[],
): (string | number)[][] {
  const out: (string | number)[][] = [];
  let prevDate: string | null = null;
  for (const row of rows) {
    if (prevDate != null && row.summary_date !== prevDate) {
      const width = mapRow(row).length;
      out.push(Array.from({ length: width }, () => ""));
    }
    out.push(mapRow(row));
    prevDate = row.summary_date;
  }
  return out;
}
