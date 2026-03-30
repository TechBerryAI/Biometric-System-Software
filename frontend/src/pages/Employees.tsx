import { useCallback, useEffect, useState } from "react";
import { fetchEmployees } from "@/services/api";
import type { Employee } from "@/types";

export function Employees() {
  const [rows, setRows] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchEmployees();
      setRows(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load employees");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="text-ink-600">Loading employees…</p>;
  }

  if (error) {
    return (
      <div className="rounded-xl border border-warn/30 bg-orange-50 p-6 text-warn">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-ink-950">Employees</h2>
        <p className="mt-1 text-sm text-ink-600">
          <code className="rounded bg-white px-1.5 py-0.5 text-xs">device_user_id</code> matches
          the terminal user id — never invented locally.
        </p>
      </div>

      <div className="rounded-2xl border border-ink-800/10 bg-white shadow-sm overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-mist/80 text-xs uppercase text-ink-600">
            <tr>
              <th className="px-6 py-3">ID</th>
              <th className="px-6 py-3">Name</th>
              <th className="px-6 py-3">Device user id</th>
              <th className="px-6 py-3">Department</th>
              <th className="px-6 py-3">Shift</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-800/10">
            {rows.map((e) => (
              <tr key={e.id} className="hover:bg-mist/40">
                <td className="px-6 py-3 text-ink-600">{e.id}</td>
                <td className="px-6 py-3 font-medium text-ink-950">{e.name}</td>
                <td className="px-6 py-3">
                  <span className="rounded-md bg-teal-50 px-2 py-1 font-mono text-xs text-accent">
                    {e.device_user_id}
                  </span>
                </td>
                <td className="px-6 py-3 text-ink-600">{e.department ?? "—"}</td>
                <td className="px-6 py-3 text-ink-600 text-xs">
                  {e.shift_start && e.shift_end
                    ? `${e.shift_start} – ${e.shift_end}`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
