import { useQuery } from "@tanstack/react-query";
import { addDays, formatISO } from "@/lib/dates";
import { fetchAttendanceLogs } from "@/services/api";

export function useRecentLogs(limit = 14) {
  return useQuery({
    queryKey: ["recent-attendance-logs", limit],
    queryFn: async () => {
      const from = formatISO(addDays(new Date(), -3));
      const logs = await fetchAttendanceLogs({ from });
      return logs.slice(0, limit);
    },
  });
}
