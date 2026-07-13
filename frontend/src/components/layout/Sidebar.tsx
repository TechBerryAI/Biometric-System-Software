import { motion } from "framer-motion";
import {
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Crown,
  FileBarChart2,
  LayoutDashboard,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Settings,
  Users,
  Wifi,
} from "lucide-react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { accountTierFromUser } from "@/auth/sessionCapabilities";
import type { Permission } from "@/auth/permissions";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";
import { Button } from "@/components/ui/button";
import { fetchOperationalMetrics, formatSyncErrorMessage, syncFromDevice } from "@/services/api";

const items = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, permission: "dashboard:view" as Permission },
  { to: "/employees", label: "Employees", icon: Users, permission: "employee:view" as Permission },
  { to: "/attendance", label: "Attendance", icon: ClipboardList, permission: "reports:read" as Permission },
  { to: "/reports", label: "Reports", icon: FileBarChart2, permission: "anomaly:manage" as Permission },
  { to: "/operations", label: "Operations", icon: ShieldCheck, permission: "device:manage" as Permission },
  { to: "/settings", label: "Settings", icon: Settings, permission: "metrics:read" as Permission },
] as const;

export function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);
  const { can, user } = useAuth();
  const queryClient = useQueryClient();
  const [syncing, setSyncing] = useState(false);
  const [syncState, setSyncState] = useState<{ tone: "ok" | "warn"; message: string } | null>(null);
  const accountTier = accountTierFromUser(user);
  const visibleItems = items.filter((item) => can(item.permission));
  const opsMetrics = useQuery({
    queryKey: ["operational-metrics"],
    queryFn: fetchOperationalMetrics,
    staleTime: 45 * 1000,
    refetchInterval: 45 * 1000,
    retry: false,
  });
  const failingDevices = opsMetrics.data?.failing_devices ?? 0;
  const retryPressure = (opsMetrics.data?.stale_commands ?? 0) + (opsMetrics.data?.dead_letter_commands ?? 0);
  const manualSyncMode = opsMetrics.data?.device_auto_sync_enabled === false;
  const deviceHealth = opsMetrics.data?.device_health_status ?? "UNKNOWN";
  const queueOk = failingDevices === 0 && retryPressure === 0;
  const syncHealthy = manualSyncMode ? queueOk : deviceHealth === "ONLINE" && queueOk;
  const showOffline = !manualSyncMode && deviceHealth === "OFFLINE";
  const statusLabel = manualSyncMode
    ? queueOk
      ? "Ready"
      : "Degraded"
    : syncHealthy
      ? "Healthy"
      : showOffline
        ? "Offline"
        : "Degraded";
  const deviceTarget =
    opsMetrics.data?.device_ip && opsMetrics.data?.device_port
      ? `${opsMetrics.data.device_ip}:${opsMetrics.data.device_port}`
      : null;

  const refreshWorkforceViews = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["employees"] }),
      queryClient.invalidateQueries({ queryKey: ["recent-attendance-logs"] }),
      queryClient.invalidateQueries({ queryKey: ["attendance-trend"] }),
      queryClient.invalidateQueries({ queryKey: ["operational-metrics"] }),
      queryClient.invalidateQueries({ queryKey: ["attendance-anomalies"] }),
      queryClient.invalidateQueries({ queryKey: ["management-insights"] }),
    ]);
  };

  const onSyncNow = async () => {
    setSyncing(true);
    setSyncState(null);
    try {
      const result = await syncFromDevice();
      await refreshWorkforceViews();
      window.dispatchEvent(new Event("biometrica:device-sync"));
      setSyncState({
        tone: "ok",
        message: `Synced ${result.new_attendance_logs} new logs from ${result.attendance_records_fetched} fetched records.`,
      });
    } catch (error: unknown) {
      setSyncState({
        tone: "warn",
        message: formatSyncErrorMessage(error) || "Sync failed. Check device connectivity and retry.",
      });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 72 : 248 }}
      transition={{ type: "spring", stiffness: 420, damping: 38 }}
      className={cn(
        "sticky top-0 z-40 flex h-screen shrink-0 flex-col overflow-hidden border-r border-line/70 bg-surface-card shadow-nav",
        accountTier === "operator" &&
          "border-red-200/80 bg-[linear-gradient(180deg,#fff5f5_0%,#ffffff_12%,#ffffff_100%)]",
        accountTier === "ceo" && "border-status-late-soft/80 bg-[linear-gradient(180deg,#fffcf1_0%,#ffffff_12%,#ffffff_100%)]",
        accountTier === "hr" && "border-primary/15 bg-[linear-gradient(180deg,#f5f7ff_0%,#ffffff_12%,#ffffff_100%)]"
      )}
    >
      <div className="flex h-20 items-center justify-between gap-2 border-b border-line/60 px-3">
        <div className={cn("flex min-w-0 items-center gap-2", collapsed && "justify-center w-full")}>
          <div
            className={cn(
              "relative flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-2xl shadow-sm",
              accountTier === "operator" &&
                "bg-[radial-gradient(circle_at_30%_20%,#FCA5A5_0%,#DC2626_60%,#991B1B_100%)] text-white",
              accountTier === "ceo" &&
                "bg-[radial-gradient(circle_at_30%_20%,#FDE68A_0%,#CA8A04_60%,#854D0E_100%)] text-white",
              accountTier === "hr" &&
                "bg-[radial-gradient(circle_at_30%_20%,#A5B4FC_0%,#4F46E5_60%,#312E81_100%)] text-white",
              accountTier === "other" &&
                "bg-[radial-gradient(circle_at_30%_20%,#C4B5FD_0%,#7C3AED_60%,#4C1D95_100%)] text-white"
            )}
          >
            <Crown className="h-5 w-5" strokeWidth={1.9} />
            <Sparkles className="absolute -right-1 -top-1 h-3 w-3 opacity-80" strokeWidth={2} />
          </div>
          {!collapsed ? (
            <div className="min-w-0">
              <p className="text-[15px] font-semibold leading-tight text-ink tracking-tight">Biometrica</p>
              <p className="text-[11px] leading-tight text-ink-muted">Attendance Command</p>
            </div>
          ) : null}
        </div>
        {!collapsed ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-ink-muted"
            onClick={toggle}
            aria-label="Collapse sidebar"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
        ) : null}
      </div>

      {!collapsed ? (
        <div className="border-b border-line/60 px-3 py-3">
          <div className="rounded-2xl border border-line/70 bg-surface px-3 py-2 shadow-sm">
            <p className="text-[10px] uppercase tracking-[0.14em] text-ink-muted">Workspace</p>
            <div className="mt-1 flex items-center justify-between">
              <p className="text-sm font-semibold text-ink">Global HQ</p>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] font-semibold",
                  accountTier === "operator"
                    ? "bg-red-100 text-red-700"
                    : "bg-primary-soft text-primary"
                )}
              >
                Live
              </span>
            </div>
          </div>
        </div>
      ) : null}

      {collapsed ? (
        <div className="flex justify-center py-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-ink-muted"
            onClick={toggle}
            aria-label="Expand sidebar"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      ) : null}

      <nav className="flex flex-1 flex-col gap-1 p-2.5">
        {visibleItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                collapsed && "justify-center px-0",
                isActive
                  ? accountTier === "operator"
                    ? "bg-red-50 text-red-700 shadow-sm ring-1 ring-red-200/80"
                    : accountTier === "ceo"
                    ? "bg-status-late-soft/80 text-status-late shadow-sm ring-1 ring-status-late/15"
                    : accountTier === "hr"
                    ? "bg-primary-soft text-primary shadow-sm ring-1 ring-primary/10"
                    : "bg-primary-soft text-primary shadow-sm ring-1 ring-primary/10"
                  : "text-ink-muted hover:bg-surface hover:text-ink hover:shadow-sm"
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && !collapsed ? (
                  <motion.span
                    layoutId="sidebar-active-pill"
                    className={cn(
                      "absolute left-1.5 top-1/2 h-6 w-1 -translate-y-1/2 rounded-full",
                      accountTier === "operator" ? "bg-red-600" : "bg-primary"
                    )}
                  />
                ) : null}
                <Icon className="h-[18px] w-[18px] shrink-0 stroke-[1.75]" />
                {!collapsed ? <span className="truncate">{label}</span> : null}
                {!collapsed && label === "Operations" && retryPressure > 0 ? (
                  <span className="ml-auto rounded-full bg-status-absent-soft px-1.5 py-0.5 text-[10px] font-semibold text-status-absent">
                    {retryPressure}
                  </span>
                ) : null}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className={cn("mt-auto border-t border-line/60 p-3", collapsed && "px-2")}>
        {!collapsed ? (
          <div className="space-y-2">
            <div className="rounded-2xl border border-line/70 bg-surface px-3 py-2.5 text-[11px] leading-snug text-ink-muted shadow-sm">
              <p className="flex items-center justify-between font-medium text-ink/80">
                <span>Device sync health</span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1",
                    syncHealthy ? "text-emerald-600" : showOffline ? "text-red-600" : "text-amber-600"
                  )}
                >
                  <span
                    className={cn(
                      "h-2 w-2 animate-pulse rounded-full",
                      syncHealthy ? "bg-emerald-500" : showOffline ? "bg-red-500" : "bg-amber-500"
                    )}
                  />
                  {statusLabel}
                </span>
              </p>
              <p className="mt-1 flex items-center gap-1">
                <Wifi className="h-3.5 w-3.5 text-primary" />
                {opsMetrics.isLoading
                  ? "Checking live device status..."
                  : manualSyncMode
                    ? "Manual sync — use Sync now to pull from terminal"
                    : syncHealthy
                      ? `${failingDevices} devices failing, ${retryPressure} sync retries pending`
                      : `Device offline${deviceTarget ? ` (${deviceTarget})` : ""} — check connectivity`}
              </p>
            </div>
            <div className="grid grid-cols-1 gap-2">
              <Button
                variant="secondary"
                size="sm"
                className="rounded-xl text-xs"
                onClick={() => void onSyncNow()}
                disabled={syncing}
              >
                <RefreshCw className={cn("h-3.5 w-3.5", syncing && "animate-spin")} />
                Sync now
              </Button>
            </div>
            {syncState ? (
              <p
                className={cn(
                  "rounded-xl px-2 py-1 text-[11px]",
                  syncState.tone === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
                )}
              >
                {syncState.message}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </motion.aside>
  );
}
