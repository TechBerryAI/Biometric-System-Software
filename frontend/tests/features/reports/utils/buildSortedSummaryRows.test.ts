import { describe, expect, it } from "vitest";
import { buildSortedSummaryRows } from "@/features/reports/utils/buildSortedSummaryRows";
import type { DailySummaryRow } from "@/types";

function row(
  partial: Pick<DailySummaryRow, "employee_id" | "employee_name" | "first_check_in"> &
    Partial<DailySummaryRow>,
): DailySummaryRow {
  return {
    summary_date: partial.summary_date ?? "2026-07-01",
    device_user_id: String(partial.employee_id),
    last_check_out: null,
    total_work_minutes: partial.total_work_minutes ?? 480,
    sessions_count: 1,
    ...partial,
  };
}

describe("FE-UNIT-REP-SORT-001 buildSortedSummaryRows", () => {
  it("sorts each day independently (late first) without global ranking", () => {
    const day1 = "2026-07-15";
    const day2 = "2026-07-16";
    const byDay: Record<string, DailySummaryRow[]> = {
      [day1]: [
        row({ employee_id: 1, employee_name: "Early Bird", first_check_in: `${day1}T08:00:00Z` }),
        row({ employee_id: 2, employee_name: "Late Comer", first_check_in: `${day1}T11:00:00Z` }),
      ],
      [day2]: [
        row({ employee_id: 1, employee_name: "Early Bird", first_check_in: `${day2}T10:30:00Z` }),
        row({ employee_id: 2, employee_name: "Late Comer", first_check_in: `${day2}T09:00:00Z` }),
      ],
    };

    const out = buildSortedSummaryRows(byDay, [day1, day2], "late_first");

    expect(out.map((r) => `${r.summary_date}:${r.employee_name}`)).toEqual([
      `${day1}:Late Comer`,
      `${day1}:Early Bird`,
      `${day2}:Early Bird`,
      `${day2}:Late Comer`,
    ]);
  });

  it("keeps chronological day order for name sort", () => {
    const byDay: Record<string, DailySummaryRow[]> = {
      "2026-07-20": [
        row({ employee_id: 2, employee_name: "Zoe", first_check_in: "2026-07-20T09:00:00Z" }),
        row({ employee_id: 1, employee_name: "Amy", first_check_in: "2026-07-20T10:00:00Z" }),
      ],
      "2026-07-21": [
        row({ employee_id: 2, employee_name: "Zoe", first_check_in: "2026-07-21T09:00:00Z" }),
        row({ employee_id: 1, employee_name: "Amy", first_check_in: "2026-07-21T08:00:00Z" }),
      ],
    };

    const out = buildSortedSummaryRows(byDay, ["2026-07-20", "2026-07-21"], "name_asc");
    expect(out.map((r) => `${r.summary_date}:${r.employee_name}`)).toEqual([
      "2026-07-20:Amy",
      "2026-07-20:Zoe",
      "2026-07-21:Amy",
      "2026-07-21:Zoe",
    ]);
  });
});
