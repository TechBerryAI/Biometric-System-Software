import { useQuery } from "@tanstack/react-query";
import { addDays, formatISO } from "@/lib/dates";
import { fetchAttendanceLogs } from "@/features/attendance/api";

export function useRecentLogs(limit = 14) {
  return useQuery({
    queryKey: ["recent-attendance-logs", limit],
    queryFn: async () => {
      const from = formatISO(addDays(new Date(), -7));
      const logs = await fetchAttendanceLogs({ from, limit: Math.max(limit, 100) });
      return logs.slice(0, limit);
    },
  });
}
