import { Bell, Search } from "lucide-react";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
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

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function TopBar({ className }: { className?: string }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  const onSearchKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key !== "Enter") return;
      const t = q.trim();
      if (!t) return;
      navigate(`/employees?q=${encodeURIComponent(t)}`);
    },
    [navigate, q]
  );

  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line/70 bg-surface-card/90 px-4 shadow-nav backdrop-blur-md sm:px-6",
        className
      )}
    >
      <div className="relative mx-auto w-full max-w-xl flex-1">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onSearchKeyDown}
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
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-soft text-xs font-semibold text-violet">
                {initials("Admin User")}
              </span>
              <span className="hidden text-left text-sm lg:block">
                <span className="block font-medium text-ink">Admin</span>
                <span className="block text-xs text-ink-muted">Operator</span>
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuLabel>Session</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => navigate("/settings")}>Settings</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => navigate("/reports")}>Reports</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
