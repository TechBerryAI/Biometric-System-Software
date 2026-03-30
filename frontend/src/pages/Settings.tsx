import { Cpu, Globe2, Moon, Sun, Timer } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

export function Settings() {
  return (
    <div className="space-y-10">
      <header>
        <h1 className="font-display text-display-xl text-ink">Settings</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          Operational preferences and integration anchors. Sensitive values stay in your backend{" "}
          <code className="rounded-lg bg-surface-card px-1.5 py-0.5 font-mono text-xs shadow-sm">.env</code> — this
          view documents what to configure.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-soft text-primary">
                <Cpu className="h-4 w-4" strokeWidth={1.75} />
              </span>
              <div>
                <CardTitle>Device bridge</CardTitle>
                <CardDescription>ZKTeco / ESSL read-only path via pyzk.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              <label className="text-xs font-medium text-ink-muted">Device IP (env)</label>
              <Input readOnly placeholder="ZK_DEVICE_IP" className="bg-surface/50" />
            </div>
            <div className="grid gap-2">
              <label className="text-xs font-medium text-ink-muted">Device port (env)</label>
              <Input readOnly placeholder="ZK_DEVICE_PORT" className="bg-surface/50" />
            </div>
            <p className="rounded-xl bg-surface px-4 py-3 text-xs text-ink-muted leading-relaxed">
              The API only calls <span className="font-medium text-ink">get_users</span> and{" "}
              <span className="font-medium text-ink">get_attendance</span>. No templates, no destructive writes.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
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
              Default shift start used for late detection is configured with{" "}
              <code className="rounded-md bg-surface px-1 font-mono text-xs">default_shift_start</code> in backend
              settings. Set explicit windows when adding employees from the directory.
            </p>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">Grace rules</Badge>
              <Badge variant="outline">Timezone aware</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-soft text-violet">
                <Globe2 className="h-4 w-4" strokeWidth={1.75} />
              </span>
              <div>
                <CardTitle>Timezone & locale</CardTitle>
                <CardDescription>Rollups follow the server timezone.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2">
              <label className="text-xs font-medium text-ink-muted">TIMEZONE (env)</label>
              <Input readOnly placeholder="e.g. Asia/Kolkata" className="bg-surface/50" />
            </div>
            <p className="text-xs text-ink-muted leading-relaxed">
              Daily summaries and charts interpret punches in this zone. Change requires backend restart.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-surface text-ink-muted ring-1 ring-line">
                  <Sun className="h-4 w-4" strokeWidth={1.75} />
                </span>
                <div>
                  <CardTitle>Appearance</CardTitle>
                  <CardDescription>Light experience by design.</CardDescription>
                </div>
              </div>
              <Badge variant="outline" className="gap-1">
                <Moon className="h-3 w-3 opacity-40" />
                Light only
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-ink-muted leading-relaxed">
              This dashboard stays in a bright, low-fatigue palette suitable for control rooms and HR desks. Dark mode
              is intentionally disabled to keep contrast and printouts consistent.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
