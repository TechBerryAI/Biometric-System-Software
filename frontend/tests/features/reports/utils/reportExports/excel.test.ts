import { beforeEach, describe, expect, it, vi } from "vitest";
import { downloadAttendanceSummaryExcel } from "@/features/reports/utils/reportExports/excel";

vi.mock("xlsx", async () => {
  const actual = await vi.importActual<typeof import("xlsx")>("xlsx");
  return {
    ...actual,
    writeFile: vi.fn(),
  };
});

describe("FE-UNIT-XLS-001 reportExports excel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("builds attendance summary workbook without throwing", async () => {
    const XLSX = await import("xlsx");
    downloadAttendanceSummaryExcel({
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
    expect(XLSX.writeFile).toHaveBeenCalled();
  });
});
