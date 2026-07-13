import { useQuery } from "@tanstack/react-query";
import { fetchDailySummaryRange } from "@/services/api";
import { trailingDayISOs, fmtChartDayLabel } from "@/lib/dates";

export type TrendPoint = {
  date: string;
  label: string;
  present: number;
  absent: number;
  /** Rows returned for that day (matches current roster size). */
  headcount: number;
  /** % of roster with at least one punch. */
  attendanceRatePercent: number;
  /** Average in→out minutes for present rows with both punches. */
  avgWorkMinutes: number | null;
  sumWorkMinutes: number;
};

export function useAttendanceTrend(days = 14) {
  return useQuery({
    queryKey: ["attendance-trend", days],
    staleTime: 5 * 60 * 1000,
    queryFn: async (): Promise<TrendPoint[]> => {
      const dates = trailingDayISOs(days);
      const range = await fetchDailySummaryRange(dates[0], dates[dates.length - 1]);
      return dates.map((date) => {
        const rows = range[date] ?? [];
        const headcount = rows.length;
        const present = rows.filter((r) => r.first_check_in != null).length;
        const absent = rows.filter((r) => r.first_check_in == null).length;
        const withSpan = rows.filter(
          (r) => r.first_check_in != null && r.total_work_minutes != null
        );
        const sumWorkMinutes = withSpan.reduce((s, r) => s + (r.total_work_minutes ?? 0), 0);
        const avgWorkMinutes = withSpan.length > 0 ? sumWorkMinutes / withSpan.length : null;
        return {
          date,
          label: fmtChartDayLabel(date),
          present,
          absent,
          headcount,
          attendanceRatePercent: headcount > 0 ? (present / headcount) * 100 : 0,
          avgWorkMinutes,
          sumWorkMinutes,
        };
      });
    },
  });
}
