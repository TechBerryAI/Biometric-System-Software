import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-ink-800 text-white shadow-sm"
      : "text-ink-600 hover:bg-white/60 hover:text-ink-950",
  ].join(" ");

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-ink-800/10 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4">
          <div>
            <h1 className="font-display text-xl font-bold tracking-tight text-ink-950">
              Attendance
            </h1>
            <p className="text-xs text-ink-600">Biometric read-only shadow mode</p>
          </div>
          <nav className="flex flex-wrap gap-1">
            <NavLink to="/" className={linkClass} end>
              Dashboard
            </NavLink>
            <NavLink to="/employees" className={linkClass}>
              Employees
            </NavLink>
            <NavLink to="/attendance" className={linkClass}>
              Attendance
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
    </div>
  );
}
