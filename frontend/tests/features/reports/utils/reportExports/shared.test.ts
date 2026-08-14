import { describe, expect, it } from "vitest";
import {
  fmtMinutes,
  formatExtension,
  mapRowsWithDaySeparators,
  safeFilename,
} from "@/features/reports/utils/reportExports/shared";

describe("FE-UNIT-EXP-SHARED-001 reportExports shared", () => {
  it("formats minutes, filenames, and extensions", () => {
    expect(fmtMinutes(null)).toBe("—");
    expect(fmtMinutes(75)).toBe("01:15");
    expect(safeFilename("Ada Lovelace Report!")).toBe("ada_lovelace_report");
    expect(formatExtension("pdf")).toBe("pdf");
    expect(formatExtension("word")).toBe("docx");
    expect(formatExtension("excel")).toBe("xlsx");
  });

  it("inserts a blank separator when the day changes", () => {
    const rows = [
      { summary_date: "2026-07-15", name: "A" },
      { summary_date: "2026-07-15", name: "B" },
      { summary_date: "2026-07-16", name: "C" },
    ];
    const mapped = mapRowsWithDaySeparators(rows, (r) => [r.summary_date, r.name]);
    expect(mapped).toEqual([
      ["2026-07-15", "A"],
      ["2026-07-15", "B"],
      ["", ""],
      ["2026-07-16", "C"],
    ]);
  });
});
