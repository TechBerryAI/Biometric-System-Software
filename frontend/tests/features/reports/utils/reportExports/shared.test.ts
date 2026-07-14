import { describe, expect, it } from "vitest";
import { fmtMinutes, formatExtension, safeFilename } from "@/features/reports/utils/reportExports/shared";

describe("FE-UNIT-EXP-SHARED-001 reportExports shared", () => {
  it("formats minutes, filenames, and extensions", () => {
    expect(fmtMinutes(null)).toBe("—");
    expect(fmtMinutes(75)).toBe("01:15");
    expect(safeFilename("Ada Lovelace Report!")).toBe("ada_lovelace_report");
    expect(formatExtension("pdf")).toBe("pdf");
    expect(formatExtension("word")).toBe("docx");
    expect(formatExtension("excel")).toBe("xlsx");
  });
});
