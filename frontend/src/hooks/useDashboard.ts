import { useQuery } from "@tanstack/react-query";
import { fetchDailySummary, fetchEmployees } from "@/services/api";
import type { DailySummaryRow, Employee } from "@/types";

export function useDashboard() {
  const employeesQuery = useQuery({
    queryKey: ["employees"],
    queryFn: fetchEmployees,
    staleTime: 5 * 60 * 1000,
  });

  const summaryQuery = useQuery({
    queryKey: ["daily-summary", "today"],
    queryFn: () => fetchDailySummary(),
    staleTime: 2 * 60 * 1000,
  });

  const employees = employeesQuery.data ?? [];
  const summary = summaryQuery.data ?? [];
  const loading = employeesQuery.isLoading || summaryQuery.isLoading;
  const error =
    employeesQuery.error instanceof Error
      ? employeesQuery.error.message
      : summaryQuery.error instanceof Error
        ? summaryQuery.error.message
        : null;

  const presentToday = summary.filter((r) => r.first_check_in != null).length;
  const absentToday = summary.filter((r) => r.first_check_in == null).length;

  const reload = async () => {
    await Promise.all([employeesQuery.refetch(), summaryQuery.refetch()]);
  };

  return {
    employees,
    summary,
    loading,
    error,
    reload,
    presentToday,
    absentToday,
    totalEmployees: employees.length,
  };
}
