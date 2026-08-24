import { useQuery } from "@tanstack/react-query";
import { fetchAttendanceLogs } from "@/features/attendance/api";
import { fetchDeviceUptime } from "@/features/monitoring/api";
import { fetchOperationalMetrics } from "@/features/operations/api";
import { formatISO } from "@/lib/dates";
import { useTenantStore } from "@/stores/tenant-store";

export function useRealtimeFeed(limit = 30) {
  const tenantId = useTenantStore((s) => s.selectedTenantId);

  const logs = useQuery({
    queryKey: ["realtime-attendance-logs", tenantId, limit],
    queryFn: async () => {
      const from = formatISO(new Date(Date.now() - 1 * 86_400_000));
      const rows = await fetchAttendanceLogs({ from, limit: Math.max(limit, 100) });
      return rows.slice(0, limit);
    },
    refetchInterval: 15_000,
  });

  const ops = useQuery({
    queryKey: ["operational-metrics", tenantId],
    queryFn: fetchOperationalMetrics,
    refetchInterval: 30_000,
  });

  const uptime = useQuery({
    queryKey: ["device-uptime", tenantId, 7],
    queryFn: () => fetchDeviceUptime(7),
    refetchInterval: 60_000,
  });

  return { logs, ops, uptime };
}
