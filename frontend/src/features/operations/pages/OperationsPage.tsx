import { useQuery } from "@tanstack/react-query";
import { fetchDeviceCommands, fetchOperationalMetrics } from "@/features/operations/api";
import { fmtDisplayDateTime } from "@/lib/dates";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function Operations() {
  const metrics = useQuery({ queryKey: ["operational-metrics"], queryFn: fetchOperationalMetrics, refetchInterval: 30000 });
  const commands = useQuery({ queryKey: ["ops-commands"], queryFn: () => fetchDeviceCommands(), refetchInterval: 30000 });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-display-xl text-ink">Operations Center</h1>
        <p className="mt-2 text-sm text-ink-muted">Device command queue and operational metrics.</p>
      </header>

      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard title="Queue depth" value={metrics.data?.queue_depth} />
        <MetricCard title="Stale commands" value={metrics.data?.stale_commands} />
        <MetricCard title="Dead letters" value={metrics.data?.dead_letter_commands} />
        <MetricCard title="Failing devices" value={metrics.data?.failing_devices} />
        <MetricCard
          title="Incomplete days"
          value={metrics.data?.incomplete_attendance_days}
          warn={(metrics.data?.incomplete_attendance_days ?? 0) > 0}
        />
      </div>

      <p className="text-sm text-ink-muted">
        Connectivity mode: {metrics.data?.device_connectivity_mode ?? "—"}
        {metrics.data?.attendance_sync_stale ? (
          <span className="ml-2 font-medium text-amber-700">Attendance sync is stale</span>
        ) : null}
      </p>

      {metrics.data?.last_attendance_sync_at ? (
        <p className="text-sm text-ink-muted">
          Last attendance sync: {fmtDisplayDateTime(metrics.data.last_attendance_sync_at)}
        </p>
      ) : (
        <p className="text-sm font-medium text-amber-700">No successful attendance sync recorded yet.</p>
      )}

      {(metrics.data?.incomplete_attendance_samples?.length ?? 0) > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Incomplete attendance days</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-line/60 text-left text-ink-muted">
                  <th className="py-2 pr-3">Employee</th>
                  <th className="py-2 pr-3">Date</th>
                  <th className="py-2 pr-3">Punches</th>
                  <th className="py-2 pr-3">First</th>
                  <th className="py-2 pr-3">Last</th>
                </tr>
              </thead>
              <tbody>
                {(metrics.data?.incomplete_attendance_samples ?? []).map((row) => (
                  <tr key={`${row.employee_code}-${row.local_date}`} className="border-b border-line/40">
                    <td className="py-2 pr-3 font-mono text-xs">{row.employee_code}</td>
                    <td className="py-2 pr-3">{row.local_date}</td>
                    <td className="py-2 pr-3">{row.punch_count}</td>
                    <td className="py-2 pr-3">{row.first_punch ? fmtDisplayDateTime(row.first_punch) : "—"}</td>
                    <td className="py-2 pr-3">{row.last_punch ? fmtDisplayDateTime(row.last_punch) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Device Command Queue</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead>
              <tr className="border-b border-line/60 text-left text-ink-muted">
                <th className="py-2 pr-3">Command</th>
                <th className="py-2 pr-3">Type</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Retries</th>
                <th className="py-2 pr-3">Created</th>
                <th className="py-2 pr-3">Error</th>
              </tr>
            </thead>
            <tbody>
              {(commands.data ?? []).slice(0, 30).map((row) => (
                <tr key={row.command_uuid} className="border-b border-line/40">
                  <td className="py-2 pr-3 font-mono text-xs">{row.command_uuid}</td>
                  <td className="py-2 pr-3">{row.command_type}</td>
                  <td className="py-2 pr-3">{row.status}</td>
                  <td className="py-2 pr-3">{row.retries}</td>
                  <td className="py-2 pr-3">{fmtDisplayDateTime(row.created_at)}</td>
                  <td className="py-2 pr-3 text-xs text-ink-muted">{row.last_error ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({
  title,
  value,
  warn = false,
}: {
  title: string;
  value: number | undefined;
  warn?: boolean;
}) {
  return (
    <Card className={warn ? "border-amber-300/80 bg-amber-50/40" : undefined}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className={`font-display text-2xl ${warn ? "text-amber-800" : "text-ink"}`}>
          {typeof value === "number" ? value : "-"}
        </p>
      </CardContent>
    </Card>
  );
}
