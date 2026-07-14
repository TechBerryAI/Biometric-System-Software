import { describe, expect, it, vi } from "vitest";
import { downloadAttendanceSummaryPdf } from "@/features/reports/utils/reportExports/pdf";

vi.mock("jspdf", () => {
  class MockJsPDF {
    internal = { pageSize: { getWidth: () => 842, getHeight: () => 595 } };
    setFillColor() {}
    rect() {}
    setDrawColor() {}
    setLineWidth() {}
    line() {}
    setTextColor() {}
    setFont() {}
    setFontSize() {}
    text() {}
    setPage() {}
    getNumberOfPages() {
      return 1;
    }
    save = vi.fn();
  }
  return { default: MockJsPDF };
});

vi.mock("jspdf-autotable", () => ({
  default: vi.fn(),
}));

describe("FE-UNIT-PDF-001 reportExports pdf", () => {
  it("calls download with minimal attendance payload", () => {
    expect(() =>
      downloadAttendanceSummaryPdf({
        periodLabel: "Day 01/06/2024",
        rows: [
          {
            summary_date: "2024-06-01",
            employee_id: 1,
            device_user_id: "1001",
            employee_name: "Ada Lovelace",
            first_check_in: "2024-06-01T09:00:00Z",
            last_check_out: "2024-06-01T17:00:00Z",
            total_work_minutes: 480,
            sessions_count: 1,
          },
        ],
      }),
    ).not.toThrow();
  });
});
