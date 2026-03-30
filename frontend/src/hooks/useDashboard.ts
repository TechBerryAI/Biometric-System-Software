import { useCallback, useEffect, useState } from "react";
import { fetchDailySummary, fetchEmployees } from "@/services/api";
import type { DailySummaryRow, Employee } from "@/types";

export function useDashboard() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [summary, setSummary] = useState<DailySummaryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [emps, sum] = await Promise.all([fetchEmployees(), fetchDailySummary()]);
      setEmployees(emps);
      setSummary(sum);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const lateCount = summary.filter((r) => r.late_arrival).length;
  const presentToday = summary.filter((r) => r.sessions_count > 0).length;

  return {
    employees,
    summary,
    loading,
    error,
    reload: load,
    lateCount,
    presentToday,
    totalEmployees: employees.length,
  };
}
