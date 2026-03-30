import { motion } from "framer-motion";
import {
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FileBarChart2,
  LayoutDashboard,
  ScanFace,
  Settings,
  Users,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";
import { Button } from "@/components/ui/button";

const items = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/employees", label: "Employees", icon: Users },
  { to: "/attendance", label: "Attendance", icon: ClipboardList },
  { to: "/reports", label: "Reports", icon: FileBarChart2 },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 72 : 248 }}
      transition={{ type: "spring", stiffness: 420, damping: 38 }}
      className="sticky top-0 z-40 flex h-screen shrink-0 flex-col overflow-hidden border-r border-line/70 bg-surface-card shadow-nav"
    >
      <div className="flex h-14 items-center justify-between gap-2 border-b border-line/60 px-3">
        <div className={cn("flex min-w-0 items-center gap-2", collapsed && "justify-center w-full")}>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
            <ScanFace className="h-5 w-5" strokeWidth={1.75} />
          </div>
          {!collapsed ? (
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink tracking-tight">Attendance</p>
              <p className="truncate text-[11px] text-ink-muted">Enterprise</p>
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

      <nav className="flex flex-1 flex-col gap-0.5 p-2">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                collapsed && "justify-center px-0",
                isActive
                  ? "bg-primary-soft text-primary shadow-sm"
                  : "text-ink-muted hover:bg-surface hover:text-ink"
              )
            }
          >
            <Icon className="h-[18px] w-[18px] shrink-0 stroke-[1.75]" />
            {!collapsed ? <span className="truncate">{label}</span> : null}
          </NavLink>
        ))}
      </nav>

      <div className={cn("mt-auto border-t border-line/60 p-3", collapsed && "px-2")}>
        {!collapsed ? (
          <p className="rounded-xl bg-surface px-3 py-2 text-[11px] leading-snug text-ink-muted">
            Read-only device sync. Identity follows terminal{" "}
            <code className="rounded bg-surface-card px-1 font-mono text-[10px] text-ink">device_user_id</code>.
          </p>
        ) : null}
      </div>
    </motion.aside>
  );
}
