import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchAuditLogs, fetchDeviceCommands, fetchOperationalMetrics } from "@/services/api";

export function Operations() {
  const metrics = useQuery({ queryKey: ["ops-metrics"], queryFn: fetchOperationalMetrics, refetchInterval: 30000 });
  const commands = useQuery({ queryKey: ["ops-commands"], queryFn: () => fetchDeviceCommands(), refetchInterval: 30000 });
  const audits = useQuery({ queryKey: ["ops-audits"], queryFn: fetchAuditLogs, refetchInterval: 30000 });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-display-xl text-ink">Operations Center</h1>
        <p className="mt-2 text-sm text-ink-muted">Device queue, reconciliation drift, and immutable audit trail.</p>
      </header>

      <div className="grid gap-4 md:grid-cols-5">
        <MetricCard title="Queue depth" value={metrics.data?.queue_depth} />
        <MetricCard title="Stale commands" value={metrics.data?.stale_commands} />
        <MetricCard title="Dead letters" value={metrics.data?.dead_letter_commands} />
        <MetricCard title="Failing devices" value={metrics.data?.failing_devices} />
        <MetricCard title="Sync drift events" value={metrics.data?.sync_drift_events} />
      </div>

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
                  <td className="py-2 pr-3">{new Date(row.created_at).toLocaleString()}</td>
                  <td className="py-2 pr-3 text-xs text-ink-muted">{row.last_error ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Audit Logs</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead>
              <tr className="border-b border-line/60 text-left text-ink-muted">
                <th className="py-2 pr-3">Time</th>
                <th className="py-2 pr-3">Action</th>
                <th className="py-2 pr-3">Entity</th>
                <th className="py-2 pr-3">Actor</th>
                <th className="py-2 pr-3">Request ID</th>
              </tr>
            </thead>
            <tbody>
              {(audits.data ?? []).slice(0, 40).map((row) => (
                <tr key={row.id} className="border-b border-line/40">
                  <td className="py-2 pr-3">{new Date(row.timestamp).toLocaleString()}</td>
                  <td className="py-2 pr-3">{row.action_type}</td>
                  <td className="py-2 pr-3">{row.entity_type}:{row.entity_id}</td>
                  <td className="py-2 pr-3 font-mono text-xs">{row.actor_user_uuid ?? "anonymous"}</td>
                  <td className="py-2 pr-3 font-mono text-xs">{row.request_id ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({ title, value }: { title: string; value: number | undefined }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-display text-2xl text-ink">{typeof value === "number" ? value : "-"}</p>
      </CardContent>
    </Card>
  );
}
