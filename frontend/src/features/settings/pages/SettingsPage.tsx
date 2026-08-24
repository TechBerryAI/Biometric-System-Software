import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, Cpu, Globe2, Loader2, Moon, ShieldCheck, Sparkles, Sun, Timer } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/features/auth/AuthContext";
import { listFleetDevices, updateFleetDevice, RETIRED_PRIMARY_IP } from "@/features/settings/api";
import { DeviceCutoverCard } from "@/features/settings/components/DeviceCutoverCard";
import { fetchOperationalMetrics } from "@/features/operations/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getApiErrorMessage } from "@/shared/api/client";

type BridgeForm = {
  ipAddress: string;
  port: string;
  timezone: string;
};

const EMPTY_FORM: BridgeForm = { ipAddress: "", port: "", timezone: "" };

const SELECT_CLASS =
  "h-10 w-full rounded-xl border border-line bg-surface-card px-3 text-sm text-ink shadow-sm transition-shadow hover:border-line focus-visible:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/15 disabled:cursor-not-allowed disabled:bg-surface/60 disabled:opacity-80";

const FALLBACK_TIMEZONES = [
  "UTC",
  "Africa/Cairo",
  "Africa/Johannesburg",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/New_York",
  "America/Sao_Paulo",
  "America/Toronto",
  "Asia/Dubai",
  "Asia/Hong_Kong",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Europe/Berlin",
  "Europe/London",
  "Europe/Paris",
  "Pacific/Auckland",
];

function listTimezones(): string[] {
  try {
    const supported = (
      Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] }
    ).supportedValuesOf?.("timeZone");
    if (supported && supported.length > 0) return supported;
  } catch {
    // Older runtimes may not support supportedValuesOf.
  }
  return FALLBACK_TIMEZONES;
}

const TIMEZONE_OPTIONS = listTimezones();

function timezoneLabel(zone: string): string {
  return zone.replace(/_/g, " ");
}

export function Settings() {
  const { can } = useAuth();
  const canManageDevice = can("device:manage");
  const queryClient = useQueryClient();
  const [form, setForm] = useState<BridgeForm>(EMPTY_FORM);
  const [baseline, setBaseline] = useState<BridgeForm>(EMPTY_FORM);
  const [deviceName, setDeviceName] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const devicesQuery = useQuery({
    queryKey: ["fleet-devices"],
    queryFn: listFleetDevices,
    enabled: canManageDevice,
    staleTime: 30_000,
    retry: false,
  });

  const metricsQuery = useQuery({
    queryKey: ["operational-metrics"],
    queryFn: fetchOperationalMetrics,
    staleTime: 30_000,
    retry: false,
  });

  const primaryDevice = useMemo(() => {
    const rows = devicesQuery.data ?? [];
    if (rows.length === 0) return null;
    return rows.find((row) => row.active) ?? rows[0];
  }, [devicesQuery.data]);

  useEffect(() => {
    if (canManageDevice && primaryDevice) {
      const next: BridgeForm = {
        ipAddress: primaryDevice.ip_address ?? "",
        port: String(primaryDevice.port ?? ""),
        timezone: primaryDevice.timezone ?? "",
      };
      setForm(next);
      setBaseline(next);
      setDeviceName(primaryDevice.name);
      return;
    }
    if (!canManageDevice && metricsQuery.data) {
      const next: BridgeForm = {
        ipAddress: metricsQuery.data.device_ip ?? "",
        port: metricsQuery.data.device_port != null ? String(metricsQuery.data.device_port) : "",
        timezone: "",
      };
      setForm(next);
      setBaseline(next);
      setDeviceName(null);
    }
  }, [canManageDevice, primaryDevice, metricsQuery.data]);

  const dirty =
    form.ipAddress !== baseline.ipAddress ||
    form.port !== baseline.port ||
    form.timezone !== baseline.timezone;

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!deviceName) {
        throw new Error("No registered device found to update.");
      }
      const port = Number(form.port);
      if (!form.ipAddress.trim()) {
        throw new Error("Device IP is required.");
      }
      if (!Number.isInteger(port) || port < 1 || port > 65535) {
        throw new Error("Device port must be an integer between 1 and 65535.");
      }
      if (!form.timezone.trim()) {
        throw new Error("Timezone is required.");
      }
      return updateFleetDevice(deviceName, {
        ip_address: form.ipAddress,
        port,
        timezone: form.timezone,
      });
    },
    onSuccess: (device) => {
      const next: BridgeForm = {
        ipAddress: device.ip_address,
        port: String(device.port),
        timezone: device.timezone,
      };
      setForm(next);
      setBaseline(next);
      setDeviceName(device.name);
      setMessage({
        type: "success",
        text: "Device connection settings saved. Sync and probes will use the new address.",
      });
      void queryClient.invalidateQueries({ queryKey: ["fleet-devices"] });
      void queryClient.invalidateQueries({ queryKey: ["operational-metrics"] });
    },
    onError: (error: unknown) => {
      setMessage({ type: "error", text: getApiErrorMessage(error) });
    },
  });

  const loading = canManageDevice ? devicesQuery.isLoading : metricsQuery.isLoading;
  const loadError = canManageDevice
    ? devicesQuery.error
      ? getApiErrorMessage(devicesQuery.error)
      : null
    : metricsQuery.error
      ? getApiErrorMessage(metricsQuery.error)
      : null;
  const readOnly = !canManageDevice;

  const timezoneOptions = useMemo(() => {
    if (form.timezone && !TIMEZONE_OPTIONS.includes(form.timezone)) {
      return [form.timezone, ...TIMEZONE_OPTIONS];
    }
    return TIMEZONE_OPTIONS;
  }, [form.timezone]);

  const updateField = (key: keyof BridgeForm, value: string) => {
    setMessage(null);
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const submit = () => {
    setMessage(null);
    saveMutation.mutate();
  };

  return (
    <div className="space-y-8">
      <header>
        <div className="rounded-3xl border border-line/70 bg-gradient-to-br from-surface-card via-surface to-primary-soft/25 p-6 shadow-card">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="font-display text-display-xl text-ink">Settings</h1>
              <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
                Manage device connectivity, shift behavior, account security, and regional preferences from one place.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="gap-1.5 bg-surface/70">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                Read-only sync
              </Badge>
              <Badge variant="outline" className="gap-1.5 bg-surface/70">
                <Clock3 className="h-3.5 w-3.5 text-primary" />
                Timezone aware
              </Badge>
              <Badge variant="outline" className="gap-1.5 bg-surface/70">
                <Sparkles className="h-3.5 w-3.5 text-violet" />
                Optimized defaults
              </Badge>
            </div>
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="border-line/70 bg-surface-card/95 shadow-card transition-shadow duration-300 hover:shadow-card-hover">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-soft text-primary">
                <Cpu className="h-4 w-4" strokeWidth={1.75} />
              </span>
              <div>
                <CardTitle>Device bridge</CardTitle>
                <CardDescription>
                  {deviceName
                    ? `ZKTeco / ESSL connection for ${deviceName}.`
                    : "ZKTeco / ESSL connection profile."}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {loading ? (
              <p className="flex items-center gap-2 text-sm text-ink-muted">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading device settings…
              </p>
            ) : null}

            {loadError ? (
              <p className="rounded-xl border border-status-absent-soft bg-status-absent-soft/40 px-3 py-2 text-sm text-status-absent">
                {loadError}
              </p>
            ) : null}

            {typeof metricsQuery.data?.device_clock_drift_seconds === "number" &&
            Math.abs(metricsQuery.data.device_clock_drift_seconds) > 120 ? (
              <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800">
                Device clock is {Math.round(Math.abs(metricsQuery.data.device_clock_drift_seconds) / 60)} minutes off
                IST. Attendance poll will rewrite the terminal to local time automatically.
              </p>
            ) : null}

            <div className="grid gap-2">
              <label htmlFor="device-ip" className="text-xs font-medium text-ink-muted">
                Device IP
              </label>
              <Input
                id="device-ip"
                value={form.ipAddress}
                onChange={(event) => updateField("ipAddress", event.target.value)}
                readOnly={readOnly}
                placeholder="e.g. 192.168.1.200"
                className={readOnly ? "bg-surface/60" : undefined}
                autoComplete="off"
              />
            </div>
            <div className="grid gap-2">
              <label htmlFor="device-port" className="text-xs font-medium text-ink-muted">
                Device port
              </label>
              <Input
                id="device-port"
                type="number"
                min={1}
                max={65535}
                value={form.port}
                onChange={(event) => updateField("port", event.target.value)}
                readOnly={readOnly}
                placeholder="e.g. 4370"
                className={readOnly ? "bg-surface/60" : undefined}
              />
            </div>
            <p className="rounded-xl border border-line/60 bg-surface px-4 py-3 text-xs text-ink-muted leading-relaxed">
              Saving IP, port, and timezone retargets the primary device <span className="font-medium text-ink">{deviceName ?? "main-entrance"}</span>.
              A replacement may keep the previous LAN address; inspect must confirm a new serial before migrating.
              {readOnly
                ? " You need device management permission to change these values."
                : " Changes apply on the next sync, probe, or inspect."}
            </p>
            {form.ipAddress.trim() === RETIRED_PRIMARY_IP ? (
              <p className="rounded-xl border border-line/60 bg-surface px-3 py-2 text-sm text-ink-muted">
                This is the previous terminal's LAN address. That is expected if the replacement uses the same IP.
                Confirm a new serial with Inspect before migrating.
              </p>
            ) : null}

            {message ? (
              <p
                className={
                  message.type === "success"
                    ? "rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
                    : "rounded-xl border border-status-absent-soft bg-status-absent-soft/40 px-3 py-2 text-sm text-status-absent"
                }
              >
                {message.text}
              </p>
            ) : null}

            {canManageDevice ? (
              <Button type="button" onClick={submit} disabled={saveMutation.isPending || !dirty || loading}>
                {saveMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving settings
                  </>
                ) : (
                  "Save device settings"
                )}
              </Button>
            ) : null}
          </CardContent>
        </Card>

        <Card className="border-line/70 bg-surface-card/95 shadow-card transition-shadow duration-300 hover:shadow-card-hover">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent/15 text-accent">
                <Timer className="h-4 w-4" strokeWidth={1.75} />
              </span>
              <div>
                <CardTitle>Shift anchors</CardTitle>
                <CardDescription>Per-employee shift overrides live on each profile.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-ink-muted leading-relaxed">
              Default shift windows power attendance context automatically. Fine-tune per employee while creating or
              editing profiles.
            </p>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">Grace rules</Badge>
              <Badge variant="outline">Timezone aware</Badge>
              <Badge variant="outline">Profile overrides</Badge>
            </div>
          </CardContent>
        </Card>

        <Card className="border-line/70 bg-surface-card/95 shadow-card transition-shadow duration-300 hover:shadow-card-hover">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-soft text-violet">
                <Globe2 className="h-4 w-4" strokeWidth={1.75} />
              </span>
              <div>
                <CardTitle>Locale & appearance</CardTitle>
                <CardDescription>Timezone and display preferences.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <div className="grid gap-2">
                <label htmlFor="device-timezone" className="text-xs font-medium text-ink-muted">
                  Timezone
                </label>
                <select
                  id="device-timezone"
                  value={form.timezone}
                  onChange={(event) => updateField("timezone", event.target.value)}
                  disabled={readOnly}
                  className={SELECT_CLASS}
                >
                  <option value="" disabled>
                    Select a timezone
                  </option>
                  {timezoneOptions.map((zone) => (
                    <option key={zone} value={zone}>
                      {timezoneLabel(zone)}
                    </option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-ink-muted leading-relaxed">
                Choose the device-local timezone. Saved with the device profile when you click Save device settings.
              </p>
            </div>

            <div className="border-t border-line/60 pt-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface text-ink-muted ring-1 ring-line">
                    <Sun className="h-3.5 w-3.5" strokeWidth={1.75} />
                  </span>
                  <div>
                    <p className="text-sm font-medium text-ink">Appearance</p>
                    <p className="mt-1 text-xs text-ink-muted leading-relaxed">
                      Bright palette for control rooms and HR desks. Dark mode stays disabled for consistent contrast
                      and printouts.
                    </p>
                  </div>
                </div>
                <Badge variant="outline" className="shrink-0 gap-1">
                  <Moon className="h-3 w-3 opacity-40" />
                  Light only
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {canManageDevice && primaryDevice ? <DeviceCutoverCard device={primaryDevice} /> : null}
    </div>
  );
}
