import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchForensicCorrectionTimeline,
  fetchForensicCorrections,
  fetchForensicDeviceSnapshots,
  fetchForensicRawEvents,
} from "@/services/api";
import { cn } from "@/lib/cn";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type AuditTab = "corrections" | "punches" | "devices";

const tabs: { id: AuditTab; label: string; description: string }[] = [
  { id: "corrections", label: "Corrections", description: "Attendance adjustments and their audit trail." },
  { id: "punches", label: "Punch log", description: "Immutable device punch history." },
  { id: "devices", label: "Devices", description: "Periodic terminal snapshots for drift checks." },
];

export function Audit() {
  const [activeTab, setActiveTab] = useState<AuditTab>("corrections");
  const [selectedUuid, setSelectedUuid] = useState<string | null>(null);

  const corrections = useQuery({
    queryKey: ["forensic-corrections"],
    queryFn: () => fetchForensicCorrections({ limit: 100 }),
  });
  const timeline = useQuery({
    queryKey: ["forensic-timeline", selectedUuid],
    queryFn: () => fetchForensicCorrectionTimeline(selectedUuid!),
    enabled: Boolean(selectedUuid),
  });
  const events = useQuery({
    queryKey: ["forensic-raw-events"],
    queryFn: () => fetchForensicRawEvents({ limit: 200 }),
    enabled: activeTab === "punches",
  });
  const snapshots = useQuery({
    queryKey: ["forensic-device-snapshots"],
    queryFn: () => fetchForensicDeviceSnapshots({ limit: 50 }),
    enabled: activeTab === "devices",
  });

  const activeMeta = tabs.find((t) => t.id === activeTab)!;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-display-xl text-ink">Audit</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          System audit logs and device history.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "rounded-xl border px-4 py-2 text-sm font-medium transition-colors",
              activeTab === tab.id
                ? "border-primary/30 bg-primary-soft text-primary shadow-sm"
                : "border-line/70 bg-surface-card text-ink-muted hover:border-line hover:text-ink"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <p className="text-sm text-ink-muted">{activeMeta.description}</p>

      {activeTab === "corrections" ? (
        <div className="grid gap-4 xl:grid-cols-5">
          <Card className="overflow-hidden xl:col-span-3">
            <CardHeader className="pb-3">
              <CardTitle>Correction ledger</CardTitle>
              <CardDescription>Select a row to inspect its timeline.</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto px-0 pb-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-t border-line/60 text-left text-xs font-medium uppercase tracking-wide text-ink-muted">
                    <th className="px-6 pb-3">Date</th>
                    <th className="px-3 pb-3">Employee</th>
                    <th className="px-3 pb-3">Status</th>
                    <th className="px-3 pb-3">Check-in</th>
                    <th className="px-6 pb-3">Check-out</th>
                  </tr>
                </thead>
                <tbody>
                  {(corrections.data ?? []).map((row) => {
                    const selected = selectedUuid === row.correction_uuid;
                    return (
                      <tr
                        key={row.correction_uuid}
                        className={cn(
                          "cursor-pointer border-t border-line/50 transition-colors",
                          selected ? "bg-primary-soft/60" : "hover:bg-surface"
                        )}
                        onClick={() => setSelectedUuid(row.correction_uuid)}
                      >
                        <td className="px-6 py-3">{row.local_date}</td>
                        <td className="px-3 py-3 tabular-nums">{row.employee_id}</td>
                        <td className="px-3 py-3">{row.status}</td>
                        <td className="px-3 py-3 text-ink-muted">{row.new_check_in ?? "—"}</td>
                        <td className="px-6 py-3 text-ink-muted">{row.new_check_out ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card className="xl:col-span-2">
            <CardHeader className="pb-3">
              <CardTitle>Timeline</CardTitle>
              <CardDescription>
                {selectedUuid ? "Events recorded for this correction." : "Pick a correction from the ledger."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {selectedUuid && timeline.data ? (
                <ul className="space-y-2 text-sm">
                  {timeline.data.events.map((e) => (
                    <li key={e.event_uuid} className="rounded-xl border border-line/60 bg-surface px-3 py-2">
                      <span className="font-medium text-ink">{e.event_type}</span>
                      <span className="mt-0.5 block text-xs text-ink-muted">{e.created_at}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-ink-muted">No correction selected.</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {activeTab === "punches" ? (
        <Card className="overflow-hidden">
          <CardHeader className="pb-3">
            <CardTitle>Raw punch events</CardTitle>
            <CardDescription>Append-only history straight from the terminal sync.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto px-0 pb-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-t border-line/60 text-left text-xs font-medium uppercase tracking-wide text-ink-muted">
                  <th className="px-6 pb-3">Timestamp</th>
                  <th className="px-3 pb-3">Employee</th>
                  <th className="px-3 pb-3">Punch</th>
                  <th className="px-6 pb-3">Source</th>
                </tr>
              </thead>
              <tbody>
                {(events.data ?? []).map((row) => (
                  <tr key={row.event_uuid} className="border-t border-line/50">
                    <td className="px-6 py-3">{row.timestamp}</td>
                    <td className="px-3 py-3">{row.employee_code}</td>
                    <td className="px-3 py-3">{row.punch_type}</td>
                    <td className="px-6 py-3 text-ink-muted">{row.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "devices" ? (
        <Card className="overflow-hidden">
          <CardHeader className="pb-3">
            <CardTitle>Device snapshots</CardTitle>
            <CardDescription>Captured terminal state over time.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto px-0 pb-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-t border-line/60 text-left text-xs font-medium uppercase tracking-wide text-ink-muted">
                  <th className="px-6 pb-3">Captured</th>
                  <th className="px-3 pb-3">Type</th>
                  <th className="px-3 pb-3">Users</th>
                  <th className="px-3 pb-3">Firmware</th>
                  <th className="px-6 pb-3">Hash</th>
                </tr>
              </thead>
              <tbody>
                {(snapshots.data ?? []).map((row) => (
                  <tr key={row.id} className="border-t border-line/50">
                    <td className="px-6 py-3">{row.captured_at}</td>
                    <td className="px-3 py-3">{row.snapshot_type}</td>
                    <td className="px-3 py-3 tabular-nums">{row.user_count}</td>
                    <td className="px-3 py-3 text-ink-muted">{row.firmware_version ?? "—"}</td>
                    <td className="px-6 py-3 font-mono text-xs text-ink-muted">{row.snapshot_hash.slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
