import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "@/auth/AuthContext";
import { accountTierFromUser } from "@/auth/privilegedAccess";
import { fetchAuditLogs, fetchDeviceCommands, fetchOperationalMetrics } from "@/services/api";
import { cn } from "@/lib/cn";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function Operations() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<"commands" | "audits">("commands");
  const accountTier = accountTierFromUser(user);
  const sliderToneClass =
    accountTier === "ceo"
      ? "bg-status-late shadow-[0_8px_22px_rgba(202,138,4,0.32)]"
      : "bg-primary shadow-[0_8px_22px_rgba(79,70,229,0.32)]";
  const activeTextClass = accountTier === "ceo" ? "text-amber-950" : "text-white";
  const metrics = useQuery({ queryKey: ["ops-metrics"], queryFn: fetchOperationalMetrics, refetchInterval: 30000 });
  const commands = useQuery({ queryKey: ["ops-commands"], queryFn: () => fetchDeviceCommands(), refetchInterval: 30000 });
  const audits = useQuery({ queryKey: ["ops-audits"], queryFn: fetchAuditLogs, refetchInterval: 30000 });

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="font-display text-display-xl text-ink">Operations Center</h1>
          <p className="mt-2 text-sm text-ink-muted">Device queue, reconciliation drift, and immutable audit trail.</p>
        </div>
        <div className="relative inline-grid grid-cols-2 rounded-2xl border border-line/70 bg-surface-card p-1 shadow-sm">
          <span
            aria-hidden
            className={cn(
              "pointer-events-none absolute left-1 top-1 h-[calc(100%-0.5rem)] w-[calc(50%-0.25rem)] rounded-xl transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]",
              sliderToneClass,
              activeTab === "commands" ? "translate-x-0" : "translate-x-full"
            )}
          />
          <button
            type="button"
            onClick={() => setActiveTab("commands")}
            className={cn(
              "relative z-10 rounded-xl px-4 py-2 text-sm font-semibold transition-all duration-300",
              activeTab === "commands"
                ? activeTextClass
                : "text-ink-muted hover:text-ink"
            )}
          >
            Command Queue
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("audits")}
            className={cn(
              "relative z-10 rounded-xl px-4 py-2 text-sm font-semibold transition-all duration-300",
              activeTab === "audits"
                ? activeTextClass
                : "text-ink-muted hover:text-ink"
            )}
          >
            Audit Logs
          </button>
        </div>
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
          <CardTitle>{activeTab === "commands" ? "Device Command Queue" : "Audit Logs"}</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {activeTab === "commands" ? (
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
          ) : (
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
                    <td className="py-2 pr-3">
                      {row.entity_type}:{row.entity_id}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{row.actor_user_uuid ?? "anonymous"}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{row.request_id ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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
