import type { ReactNode } from "react";
import { useAuth } from "@/auth/AuthContext";
import { accountTierFromUser } from "@/auth/sessionCapabilities";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppLayout({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const accountTier = accountTierFromUser(user);

  return (
    <div data-account-tier={accountTier} className="relative flex min-h-screen w-full bg-surface">
      {accountTier === "operator" ? (
        <>
          <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(90rem_50rem_at_100%_-20%,rgba(220,38,38,0.12),transparent_55%)]" />
          <div className="pointer-events-none fixed inset-0 z-0 bg-[linear-gradient(180deg,rgba(254,226,226,0.35)_0%,transparent_30%)]" />
        </>
      ) : accountTier === "ceo" ? (
        <>
          <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(90rem_50rem_at_100%_-20%,rgba(202,138,4,0.10),transparent_55%)]" />
          <div className="pointer-events-none fixed inset-0 z-0 bg-[linear-gradient(180deg,rgba(254,249,195,0.25)_0%,transparent_30%)]" />
        </>
      ) : accountTier === "hr" ? (
        <>
          <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(90rem_50rem_at_100%_-20%,rgba(79,70,229,0.10),transparent_55%)]" />
          <div className="pointer-events-none fixed inset-0 z-0 bg-[linear-gradient(180deg,rgba(238,242,255,0.35)_0%,transparent_30%)]" />
        </>
      ) : null}
      <Sidebar />
      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-x-hidden px-4 py-8 sm:px-8 lg:px-10">
          <div className="mx-auto w-full max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
