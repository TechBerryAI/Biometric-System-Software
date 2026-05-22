import { Clock3, Cpu, Globe2, Moon, ShieldCheck, Sparkles, Sun, Timer } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

export function Settings() {
  return (
    <div className="space-y-8">
      <header>
        <div className="rounded-3xl border border-line/70 bg-gradient-to-br from-surface-card via-surface to-primary-soft/25 p-6 shadow-card">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="font-display text-display-xl text-ink">Settings</h1>
              <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
                Manage device connectivity, shift behavior, and regional preferences from one place.
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
                <CardDescription>ZKTeco / ESSL connection profile.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              <label className="text-xs font-medium text-ink-muted">Device IP</label>
              <Input readOnly placeholder="e.g. 192.168.1.200" className="bg-surface/60" />
            </div>
            <div className="grid gap-2">
              <label className="text-xs font-medium text-ink-muted">Device port</label>
              <Input readOnly placeholder="e.g. 4370" className="bg-surface/60" />
            </div>
            <p className="rounded-xl border border-line/60 bg-surface px-4 py-3 text-xs text-ink-muted leading-relaxed">
              The API only calls <span className="font-medium text-ink">get_users</span> and{" "}
              <span className="font-medium text-ink">get_attendance</span>. No templates, no destructive writes.
            </p>
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
                <CardTitle>Timezone & locale</CardTitle>
                <CardDescription>Rollups follow the server timezone.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2">
              <label className="text-xs font-medium text-ink-muted">Timezone</label>
              <Input readOnly placeholder="e.g. Asia/Kolkata" className="bg-surface/60" />
            </div>
            <p className="text-xs text-ink-muted leading-relaxed">
              Daily summaries and charts interpret punches in this zone. Change requires backend restart.
            </p>
          </CardContent>
        </Card>

        <Card className="border-line/70 bg-surface-card/95 shadow-card transition-shadow duration-300 hover:shadow-card-hover">
          <CardHeader className="pb-3">
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
              The dashboard uses a bright, low-fatigue palette for control rooms and HR desks. Dark mode stays disabled
              to keep contrast and printouts consistent.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
