import { useQuery } from "@tanstack/react-query";
import { fetchDeviceCommands } from "@/features/operations/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function Audit() {
  const commands = useQuery({
    queryKey: ["audit-device-commands"],
    queryFn: () => fetchDeviceCommands(),
  });

  const correctionCommands = (commands.data ?? []).filter((row) => row.command_type === "CORRECT_ATTENDANCE");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-display-xl text-ink">Audit</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          Recent device attendance corrections. Corrections rewrite the terminal attlog and
          replace the day&apos;s attendance logs — no separate correction history is kept.
        </p>
      </header>

      <Card className="overflow-hidden">
        <CardHeader className="pb-3">
          <CardTitle>Attendance correction commands</CardTitle>
          <CardDescription>Device queue history for CORRECT_ATTENDANCE.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto px-0 pb-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-t border-line/60 text-left text-xs font-medium uppercase tracking-wide text-ink-muted">
                <th className="px-6 pb-3">Created</th>
                <th className="px-3 pb-3">Status</th>
                <th className="px-3 pb-3">Command</th>
                <th className="px-6 pb-3">Error</th>
              </tr>
            </thead>
            <tbody>
              {correctionCommands.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-ink-muted">
                    No attendance correction commands yet.
                  </td>
                </tr>
              ) : (
                correctionCommands.map((row) => (
                  <tr key={row.command_uuid} className="border-t border-line/50">
                    <td className="px-6 py-3 text-ink-muted">{row.created_at}</td>
                    <td className="px-3 py-3">{row.status}</td>
                    <td className="px-3 py-3 font-mono text-xs" title={row.command_uuid}>
                      {row.command_uuid}
                    </td>
                    <td className="px-6 py-3 text-ink-muted">{row.last_error ?? "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
