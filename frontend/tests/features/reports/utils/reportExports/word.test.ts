import { describe, expect, it, vi } from "vitest";
import { downloadAttendanceSummaryWord } from "@/features/reports/utils/reportExports/word";

vi.mock("file-saver", () => ({
  saveAs: vi.fn(),
}));

describe("FE-UNIT-DOCX-001 reportExports word", () => {
  it("exports attendance summary and triggers blob download", async () => {
    const { saveAs } = await import("file-saver");
    await downloadAttendanceSummaryWord({
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
    });
    expect(saveAs).toHaveBeenCalled();
    const [blob, filename] = vi.mocked(saveAs).mock.calls[0];
    expect(blob).toBeInstanceOf(Blob);
    expect(String(filename)).toMatch(/\.docx$/);
  });
});
