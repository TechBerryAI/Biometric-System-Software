import { useMutation } from "@tanstack/react-query";
import { Fingerprint, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import {
  RETIRED_PRIMARY_IP,
  RETIRED_PRIMARY_SERIAL,
  dryRunDeviceMigration,
  executeDeviceMigration,
  inspectReplacementDevice,
  preflightDeviceMigration,
  retryFailedDeviceMigration,
  type DeviceInspectSnapshot,
  type FleetDevice,
  type MigrationRecord,
} from "@/features/settings/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getApiErrorMessage } from "@/shared/api/client";

export function DeviceCutoverCard({ device }: { device: FleetDevice }) {
  const [inspect, setInspect] = useState<DeviceInspectSnapshot | null>(null);
  const [preflight, setPreflight] = useState<MigrationRecord | null>(null);
  const [dryRun, setDryRun] = useState<MigrationRecord | null>(null);
  const [result, setResult] = useState<MigrationRecord | null>(null);
  const [confirmName, setConfirmName] = useState(device.name);
  const [confirmIp, setConfirmIp] = useState(device.ip_address);
  const [error, setError] = useState<string | null>(null);

  const liveSerial = (inspect?.serial_number || device.serial_number || "").trim();
  const retiredSerial = liveSerial === RETIRED_PRIMARY_SERIAL;
  const sameLanAddress = device.ip_address.trim() === RETIRED_PRIMARY_IP;

  const inspectMutation = useMutation({
    mutationFn: () => inspectReplacementDevice(device.name),
    onSuccess: (data) => {
      setInspect(data);
      setError(null);
    },
    onError: (err: unknown) => setError(getApiErrorMessage(err)),
  });

  const preflightMutation = useMutation({
    mutationFn: () => preflightDeviceMigration(device.name, false),
    onSuccess: (data) => {
      setPreflight(data);
      setError(null);
    },
    onError: (err: unknown) => setError(getApiErrorMessage(err)),
  });

  const dryRunMutation = useMutation({
    mutationFn: () => dryRunDeviceMigration(device.name, false, preflight?.migration_id),
    onSuccess: (data) => {
      setDryRun(data);
      setConfirmName(device.name);
      setConfirmIp(device.ip_address);
      setError(null);
    },
    onError: (err: unknown) => setError(getApiErrorMessage(err)),
  });

  const executeMutation = useMutation({
    mutationFn: () => {
      if (!dryRun?.migration_id) {
        throw new Error("Run a dry run before migrating.");
      }
      return executeDeviceMigration(device.name, {
        dry_run_id: dryRun.migration_id,
        confirm_target_device_name: confirmName.trim(),
        confirm_target_ip: confirmIp.trim(),
      });
    },
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err: unknown) => setError(getApiErrorMessage(err)),
  });

  const retryMutation = useMutation({
    mutationFn: () => {
      const id = result?.migration_id || dryRun?.migration_id;
      if (!id) throw new Error("No migration to retry.");
      return retryFailedDeviceMigration(device.name, id, {
        confirm_target_device_name: confirmName.trim(),
        confirm_target_ip: confirmIp.trim(),
      });
    },
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err: unknown) => setError(getApiErrorMessage(err)),
  });

  const busy =
    inspectMutation.isPending ||
    preflightMutation.isPending ||
    dryRunMutation.isPending ||
    executeMutation.isPending ||
    retryMutation.isPending;

  const summary = dryRun?.preflight_summary ?? preflight?.preflight_summary;
  const failedCount = result?.report?.totals?.failed ?? 0;
  const items = useMemo(() => dryRun?.items ?? result?.items ?? [], [dryRun, result]);

  return (
    <Card className="border-line/70 bg-surface-card/95 shadow-card">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-soft text-primary">
            <Fingerprint className="h-4 w-4" strokeWidth={1.75} />
          </span>
          <div>
            <CardTitle>Replacement device cutover</CardTitle>
            <CardDescription>
            Point {device.name} at the new terminal (same LAN address is fine), inspect it, then create employee
            metadata. Fingerprints are enrolled on the device afterward.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {retiredSerial ? (
          <p className="rounded-xl border border-status-absent-soft bg-status-absent-soft/40 px-3 py-2 text-sm text-status-absent">
            Serial {RETIRED_PRIMARY_SERIAL} is the retired terminal. Inspect the replacement unit before migrating.
          </p>
        ) : (
          <p className="text-sm text-ink-muted leading-relaxed">
            Current target {device.ip_address}:{device.port}
            {liveSerial ? ` · serial ${liveSerial}` : ""}.
            {sameLanAddress
              ? " This is the previous LAN address; identity is confirmed by serial, not IP."
              : ""}
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" disabled={busy} onClick={() => inspectMutation.mutate()}>
            {inspectMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            1. Inspect
          </Button>
          <Button type="button" variant="secondary" disabled={busy || !inspect?.replacement_confirmed} onClick={() => preflightMutation.mutate()}>
            {preflightMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            2. Preflight
          </Button>
          <Button type="button" variant="secondary" disabled={busy || !inspect?.replacement_confirmed} onClick={() => dryRunMutation.mutate()}>
            {dryRunMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            3. Dry run
          </Button>
        </div>

        {inspect ? (
          <div className="flex flex-wrap gap-2">
            <Badge variant={inspect.replacement_confirmed ? "present" : "absent"}>
              {inspect.replacement_confirmed ? "Replacement confirmed" : "Not replacement hardware"}
            </Badge>
            <Badge variant="outline">Users on device {inspect.user_count}</Badge>
            {inspect.firmware_version ? <Badge variant="outline">{inspect.firmware_version}</Badge> : null}
            {inspect.serial_number ? <Badge variant="outline">{inspect.serial_number}</Badge> : null}
          </div>
        ) : null}

        {inspect?.replacement_blocker ? (
          <p className="text-sm text-status-absent">{inspect.replacement_blocker}</p>
        ) : null}

        {summary ? (
          <p className="text-sm text-ink leading-relaxed">
            TOTAL {summary.total_employees_in_scope} · CREATE {summary.create} · SKIP {summary.skip} · CONFLICT{" "}
            {summary.conflict} · VALID {summary.valid_for_migration}
          </p>
        ) : null}

        {items.length > 0 ? (
          <div className="overflow-x-auto rounded-xl border border-line/60">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-line/60 text-left text-ink-muted">
                  <th className="px-3 py-2">Employee</th>
                  <th className="px-3 py-2">Employee ID</th>
                  <th className="px-3 py-2">UID</th>
                  <th className="px-3 py-2">Card</th>
                  <th className="px-3 py-2">Action</th>
                  <th className="px-3 py-2">Conflict</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.employee_uuid} className="border-b border-line/40">
                    <td className="px-3 py-2">{row.name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{row.device_user_id}</td>
                    <td className="px-3 py-2 font-mono text-xs">{row.uid ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{row.card || "0"}</td>
                    <td className="px-3 py-2">{row.action}</td>
                    <td className="px-3 py-2 text-xs text-status-absent">{row.conflict || row.last_error || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {dryRun ? (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="grid gap-2">
              <label htmlFor="confirm-device-name" className="text-xs font-medium text-ink-muted">
                Confirm device name
              </label>
              <Input
                id="confirm-device-name"
                value={confirmName}
                onChange={(event) => setConfirmName(event.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="grid gap-2">
              <label htmlFor="confirm-device-ip" className="text-xs font-medium text-ink-muted">
                Confirm replacement IP
              </label>
              <Input
                id="confirm-device-ip"
                value={confirmIp}
                onChange={(event) => setConfirmIp(event.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="md:col-span-2 flex flex-wrap gap-2">
              <Button type="button" disabled={busy || retiredSerial} onClick={() => executeMutation.mutate()}>
                {executeMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                4. Migrate metadata
              </Button>
              {failedCount > 0 ? (
                <Button type="button" variant="secondary" disabled={busy} onClick={() => retryMutation.mutate()}>
                  Retry failed
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}

        {result ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 space-y-1">
            <p>Migration {result.status}. {result.fingerprint_next_step}</p>
            {result.report?.totals ? (
              <p>
                Created {result.report.totals.create_success}, skipped {result.report.totals.skipped}, conflicts{" "}
                {result.report.totals.conflicts}, failed {result.report.totals.failed}.
              </p>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <p className="rounded-xl border border-status-absent-soft bg-status-absent-soft/40 px-3 py-2 text-sm text-status-absent">
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}