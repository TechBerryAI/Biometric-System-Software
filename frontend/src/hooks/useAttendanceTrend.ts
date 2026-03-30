import { useQuery } from "@tanstack/react-query";
import { fetchDailySummary } from "@/services/api";
import { trailingDayISOs } from "@/lib/dates";

export type TrendPoint = {
  date: string;
  label: string;
  present: number;
  late: number;
  absent: number;
};

export function useAttendanceTrend(days = 14) {
  return useQuery({
    queryKey: ["attendance-trend", days],
    queryFn: async (): Promise<TrendPoint[]> => {
      const dates = trailingDayISOs(days);
      const summaries = await Promise.all(dates.map((d) => fetchDailySummary(d)));
      return dates.map((date, i) => {
        const rows = summaries[i] ?? [];
        const present = rows.filter((r) => r.first_check_in != null).length;
        const late = rows.filter((r) => r.late_arrival && r.first_check_in != null).length;
        const absent = rows.filter((r) => r.first_check_in == null).length;
        return {
          date,
          label: date.slice(5).replace("-", "/"),
          present,
          late,
          absent,
        };
      });
    },
  });
}
