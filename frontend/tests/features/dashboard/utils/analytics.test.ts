import { describe, expect, it } from "vitest";
import {
  computeTodayWorkStats,
  dateRangeToDays,
  formatHoursMinutes,
  healthToneFromThresholds,
  toDeltaTone,
} from "@/features/dashboard/utils/analytics";

describe("FE-UNIT-ANALYT-001 dashboardAnalytics", () => {
  it("computes work stats and formatting helpers", () => {
    const stats = computeTodayWorkStats(
      [
        {
          summary_date: "2024-06-01",
          employee_id: 1,
          device_user_id: "1",
          employee_name: "Ada",
          first_check_in: "2024-06-01T09:00:00Z",
          last_check_out: "2024-06-01T17:00:00Z",
          total_work_minutes: 480,
          sessions_count: 1,
        },
      ],
      2,
      1,
    );
    expect(stats.attendanceRate).toBe(50);
    expect(stats.avgWorkMinutesAmongPresent).toBe(480);
    expect(formatHoursMinutes(90)).toBe("1h 30m");
    expect(toDeltaTone(1)).toBe("positive");
    expect(healthToneFromThresholds(90, 80, 60)).toBe("healthy");
    expect(dateRangeToDays("Last 7 days")).toBe(7);
  });
});
