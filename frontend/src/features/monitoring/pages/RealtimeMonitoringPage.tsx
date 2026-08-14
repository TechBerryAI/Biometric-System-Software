import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, Radio, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRealtimeFeed } from "@/features/monitoring/hooks/useRealtimeFeed";
import { getApiErrorMessage } from "@/shared/api/client";
import { fmtDisplayDateTime } from "@/lib/dates";
import { cn } from "@/lib/cn";

export function RealtimeMonitoring() {
  const queryClient = useQueryClient();
  const { logs, ops, uptime } = useRealtimeFeed(40);

  useEffect(() => {
    const handler = () => {
      void queryClient.invalidateQueries({ queryKey: ["realtime-attendance-logs"] });
      void queryClient.invalidateQueries({ queryKey: ["operational-metrics"] });
      void queryClient.invalidateQueries({ queryKey: ["device-uptime"] });
    };
    window.addEventListener("biometrica:device-sync", handler);
    return () => window.removeEventListener("biometrica:device-sync", handler);
  }, [queryClient]);

  const loading = logs.isLoading || ops.isLoading;
  const error = logs.error ?? ops.error;

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-sm text-ink-muted">{getApiErrorMessage(error)}</p>
          <Button className="mt-4" onClick={() => void logs.refetch()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  const metrics = ops.data;
  const feed = logs.data ?? [];
  const uptimeRows = uptime.data?.devices ?? [];

  return (
    <div className="space-y-6">
      <header>
        <div className="flex items-center gap-2">
          <Radio className="h-5 w-5 text-primary" />
          <h1 className="font-display text-display-xl text-ink">Live Monitoring</h1>
        </div>
        <p className="mt-2 text-sm text-ink-muted">
          Real-time attendance feed, device health, and uptime signals (15s refresh).
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard
          title="Queue depth"
          value={metrics?.queue_depth}
          icon={Server}
          tone={metrics && metrics.queue_depth > 0 ? "warn" : "ok"}
        />
        <MetricCard
          title="Failing devices"
          value={metrics?.failing_devices}
          icon={AlertTriangle}
          tone={metrics && metrics.failing_devices > 0 ? "warn" : "ok"}
        />
        <MetricCard title="Live punches (24h)" value={feed.length} icon={Activity} tone="ok" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-line/60 text-left text-ink-muted">
                <th className="py-2 pr-3">Time</th>
                <th className="py-2 pr-3">Employee</th>
                <th className="py-2 pr-3">Device</th>
                <th className="py-2 pr-3">Punch</th>
              </tr>
            </thead>
            <tbody>
              {feed.map((row) => (
                <tr key={row.id} className="border-b border-line/40">
                  <td className="py-2 pr-3">{fmtDisplayDateTime(row.timestamp)}</td>
                  <td className="py-2 pr-3 font-mono text-xs">{row.employee_code}</td>
                  <td className="py-2 pr-3">{row.device_id}</td>
                  <td className="py-2 pr-3">{row.punch_type}</td>
                </tr>
              ))}
              {feed.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-ink-muted">
                    No recent punches in the last 24 hours.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Device Uptime (7d)</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-line/60 text-left text-ink-muted">
                <th className="py-2 pr-3">Device</th>
                <th className="py-2 pr-3">Uptime</th>
                <th className="py-2 pr-3">Health</th>
                <th className="py-2 pr-3">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {uptimeRows.map((row) => (
                <tr key={row.device_uuid} className="border-b border-line/40">
                  <td className="py-2 pr-3">{row.device_name}</td>
                  <td className="py-2 pr-3">{row.uptime_percent.toFixed(1)}%</td>
                  <td className="py-2 pr-3">{row.health_status}</td>
                  <td className="py-2 pr-3">{row.last_seen ? fmtDisplayDateTime(row.last_seen) : "-"}</td>
                </tr>
              ))}
              {uptimeRows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-ink-muted">
                    No active devices registered.
                  </td>
                </tr>
              ) : null}
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
  icon: Icon,
  tone,
}: {
  title: string;
  value: number | undefined;
  icon: React.ComponentType<{ className?: string }>;
  tone: "ok" | "warn";
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Icon className={cn("h-4 w-4", tone === "warn" ? "text-amber-600" : "text-primary")} />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-display text-2xl text-ink">{typeof value === "number" ? value : "-"}</p>
      </CardContent>
    </Card>
  );
}
