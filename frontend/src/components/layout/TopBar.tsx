import { Bell, Search } from "lucide-react";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { accountTierFromUser } from "@/auth/godMode";
import { AddAccountModal } from "@/components/accounts/AddAccountModal";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function TopBar({ className }: { className?: string }) {
  const navigate = useNavigate();
  const { user, logout, can } = useAuth();
  const globalSearchQuery = useUiStore((s) => s.globalSearchQuery);
  const setGlobalSearchQuery = useUiStore((s) => s.setGlobalSearchQuery);
  const [accountModalOpen, setAccountModalOpen] = useState(false);
  const canManageUsers = can("user:manage");
  const accountTier = accountTierFromUser(user);
  const roleLabel =
    accountTier === "god"
      ? "GOD mode"
      : accountTier === "ceo"
      ? "CEO"
      : user?.role === "IT_ADMIN"
      ? "IT Admin"
      : accountTier === "hr"
      ? "HR Admin"
      : user?.role ?? "No role";
  const displayName = user?.full_name?.trim() || user?.email || "Unknown user";

  const onLogout = useCallback(async () => {
    await logout();
    navigate("/login", { replace: true });
  }, [logout, navigate]);

  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line/70 bg-surface-card/90 px-4 shadow-nav backdrop-blur-md sm:px-6",
        accountTier === "god" &&
          "border-status-absent-soft/80 bg-[linear-gradient(90deg,rgba(254,226,226,0.32)_0%,rgba(255,255,255,0.92)_40%,rgba(255,255,255,0.92)_100%)]",
        accountTier === "ceo" &&
          "border-status-late-soft/90 bg-[linear-gradient(90deg,rgba(254,249,195,0.50)_0%,rgba(255,255,255,0.93)_40%,rgba(255,255,255,0.93)_100%)]",
        accountTier === "hr" &&
          "border-primary/20 bg-[linear-gradient(90deg,rgba(238,242,255,0.85)_0%,rgba(255,255,255,0.93)_40%,rgba(255,255,255,0.93)_100%)]",
        className
      )}
    >
      <div className="relative mx-auto w-full max-w-xl flex-1">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle" />
        <Input
          value={globalSearchQuery}
          onChange={(e) => setGlobalSearchQuery(e.target.value)}
          placeholder="Search employees, device ID…"
          className="h-10 border-line/80 bg-surface pl-10 pr-3 shadow-sm"
          aria-label="Search"
        />
      </div>

      <div className="flex items-center gap-1 sm:gap-2">
        <Button type="button" variant="ghost" size="icon" className="text-ink-muted" aria-label="Notifications">
          <Bell className="h-[18px] w-[18px]" strokeWidth={1.75} />
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-2 rounded-xl py-1 pl-1 pr-2 transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
            >
              <span
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-xl text-xs font-semibold",
                  accountTier === "god" && "bg-status-absent-soft text-status-absent",
                  accountTier === "ceo" && "bg-status-late-soft text-status-late",
                  accountTier === "hr" && "bg-primary-soft text-primary",
                  accountTier === "other" && "bg-violet-soft text-violet"
                )}
              >
                {initials(displayName)}
              </span>
              <span className="hidden text-left text-sm lg:block">
                <span className="block font-medium text-ink">{displayName}</span>
                <span
                  className={cn(
                    "block text-xs text-ink-muted",
                    accountTier === "god" && "font-semibold text-status-absent",
                    accountTier === "ceo" && "font-semibold text-status-late",
                    accountTier === "hr" && "font-semibold text-primary"
                  )}
                >
                  {roleLabel}
                </span>
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuLabel>Account</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => navigate("/profile")}>Profile</DropdownMenuItem>
            {canManageUsers ? (
              <DropdownMenuItem onSelect={() => setAccountModalOpen(true)}>Add New Account</DropdownMenuItem>
            ) : null}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onLogout}>Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <AddAccountModal open={accountModalOpen} onOpenChange={setAccountModalOpen} />
    </header>
  );
}
