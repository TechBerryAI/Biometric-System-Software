import { useDashboard } from "@/hooks/useDashboard";

function StatCard({
  title,
  value,
  hint,
}: {
  title: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-ink-800/10 bg-white p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-600">{title}</p>
      <p className="mt-2 font-display text-3xl font-bold text-ink-950">{value}</p>
      {hint ? <p className="mt-2 text-sm text-ink-600">{hint}</p> : null}
    </div>
  );
}

export function Dashboard() {
  const { loading, error, reload, totalEmployees, presentToday, lateCount, summary } =
    useDashboard();

  if (loading) {
    return (
      <div className="rounded-xl bg-white p-8 text-center text-ink-600 shadow-sm">
        Loading dashboard…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-warn/30 bg-orange-50 p-6 text-warn shadow-sm">
        <p className="font-medium">{error}</p>
        <button
          type="button"
          onClick={() => void reload()}
          className="mt-4 rounded-lg bg-ink-800 px-4 py-2 text-sm text-white hover:bg-ink-950"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="font-display text-2xl font-bold text-ink-950">Overview</h2>
        <p className="mt-1 text-sm text-ink-600">Today&apos;s snapshot from processed sessions</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard title="Total employees" value={totalEmployees} hint="Registered in database" />
        <StatCard
          title="Present today"
          value={presentToday}
          hint="Employees with ≥1 session today"
        />
        <StatCard
          title="Late arrivals"
          value={lateCount}
          hint="Anyone with late minutes &gt; 0"
        />
      </div>

      <div className="rounded-2xl border border-ink-800/10 bg-white shadow-sm overflow-hidden">
        <div className="border-b border-ink-800/10 px-6 py-4">
          <h3 className="font-display font-semibold text-ink-950">Today by employee</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-mist/80 text-xs uppercase text-ink-600">
              <tr>
                <th className="px-6 py-3">Name</th>
                <th className="px-6 py-3">Device ID</th>
                <th className="px-6 py-3">Sessions</th>
                <th className="px-6 py-3">Work (min)</th>
                <th className="px-6 py-3">Late</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800/10">
              {summary.map((row) => (
                <tr key={row.employee_id} className="hover:bg-mist/40">
                  <td className="px-6 py-3 font-medium text-ink-950">{row.employee_name}</td>
                  <td className="px-6 py-3 text-ink-600">{row.device_user_id}</td>
                  <td className="px-6 py-3">{row.sessions_count}</td>
                  <td className="px-6 py-3">
                    {row.total_work_minutes != null ? row.total_work_minutes : "—"}
                  </td>
                  <td className="px-6 py-3">
                    {row.late_arrival ? (
                      <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-warn">
                        Yes
                      </span>
                    ) : (
                      <span className="text-ink-600">No</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
