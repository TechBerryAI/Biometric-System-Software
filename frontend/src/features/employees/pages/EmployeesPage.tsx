import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { PenSquare, Plus, UserMinus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { AddEmployeeModal } from "@/features/employees/components/AddEmployeeModal";
import { EmployeeAvatar } from "@/features/employees/components/EmployeeAvatar";
import { OffboardEmployeeDialog } from "@/features/employees/components/OffboardEmployeeDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchEmployees, offboardEmployee } from "@/features/employees/api";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/ui-store";
import type { Employee } from "@/types";

export function Employees() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [searchParams] = useSearchParams();
  const globalSearchQuery = useUiStore((s) => s.globalSearchQuery);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null);
  const [offboardTarget, setOffboardTarget] = useState<Employee | null>(null);
  const canEditEmployees = can("employee:edit");

  useEffect(() => {
    if (searchParams.get("add") !== "1") return;
    setEditingEmployee(null);
    setModalOpen(true);
  }, [searchParams]);

  const { data: rows, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["employees"],
    queryFn: fetchEmployees,
  });

  const filtered = useMemo(() => {
    if (!rows) return [];
    const q = globalSearchQuery.trim().toLowerCase();
    const list = !q
      ? rows
      : rows.filter(
          (e) =>
            e.name.toLowerCase().includes(q) ||
            String(e.device_user_id).toLowerCase().includes(q) ||
            (e.department?.toLowerCase().includes(q) ?? false)
        );
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
  }, [rows, globalSearchQuery]);

  if (error) {
    return (
      <Card className="border-status-absent-soft bg-status-absent-soft/20">
        <CardContent className="p-8">
          <p className="text-sm font-medium text-status-absent">
            {error instanceof Error ? error.message : "Failed to load employees"}
          </p>
          <Button className="mt-4" onClick={() => void refetch()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <h1 className="font-display text-display-xl text-ink">Employees</h1>
          <p className="mt-2 max-w-xl text-sm text-ink-muted leading-relaxed">
            Directory synced from your terminal identity.{" "}
            <code className="rounded-lg bg-surface-card px-1.5 py-0.5 font-mono text-xs text-ink-muted shadow-sm">
              device_user_id
            </code>{" "}
            is authoritative — never invented locally.
          </p>
        </div>
        {canEditEmployees ? (
          <Button
            type="button"
            onClick={() => {
              setEditingEmployee(null);
              setModalOpen(true);
            }}
            className="shrink-0 shadow-sm shadow-primary/20"
          >
            <Plus className="h-4 w-4" strokeWidth={2} />
            Add employee
          </Button>
        ) : null}
      </header>

      {isFetching ? <span className="text-xs text-ink-muted">Refreshing…</span> : null}

      {canEditEmployees ? (
        <AddEmployeeModal open={modalOpen} onOpenChange={setModalOpen} employee={editingEmployee} />
      ) : null}

      {offboardTarget ? (
        <OffboardEmployeeDialog
          open={offboardTarget != null}
          onOpenChange={(open) => {
            if (!open) setOffboardTarget(null);
          }}
          employeeName={offboardTarget.name}
          deviceUserId={offboardTarget.device_user_id}
          onConfirm={async () => {
            await offboardEmployee(offboardTarget.id);
            setOffboardTarget(null);
            await refetch();
          }}
        />
      ) : null}

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-2xl" />
          ))}
        </div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="overflow-hidden rounded-2xl border border-line/70 bg-surface-card shadow-card"
        >
          <div className="scrollbar-thin overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="sticky top-0 z-[1] bg-surface/95 backdrop-blur-sm">
                <tr className="text-xs font-medium uppercase tracking-wider text-ink-muted shadow-[inset_0_-1px_0_#E2E8F0]">
                  <th className="px-6 py-3.5">Employee</th>
                  <th className="px-6 py-3.5">Device user id</th>
                  <th className="px-6 py-3.5">Department</th>
                  <th className="px-6 py-3.5">Shift</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-16 text-center">
                      <p className="text-sm font-medium text-ink">No matches</p>
                      <p className="mt-1 text-sm text-ink-muted">Try another search or add an employee.</p>
                    </td>
                  </tr>
                ) : (
                  filtered.map((e, idx) => (
                    <tr
                      key={e.id}
                      onClick={() => navigate(`/employees/${e.id}`)}
                      className={cn(
                        "cursor-pointer border-b border-line/40 transition-colors duration-150 hover:bg-surface/80",
                        idx % 2 === 1 && "bg-surface/[0.35]"
                      )}
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <EmployeeAvatar name={e.name} id={e.id} />
                          <div>
                            <p className="font-medium text-ink">{e.name}</p>
                            <p className="text-xs text-ink-muted">ID {e.id}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="rounded-lg bg-primary-soft px-2 py-1 font-mono text-xs text-primary">
                          {e.device_user_id}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-ink-muted">{e.department ?? "—"}</td>
                      <td className="px-6 py-4 text-xs text-ink-muted">
                        {e.shift_start && e.shift_end ? `${e.shift_start} – ${e.shift_end}` : "—"}
                      </td>
                      <td className="px-6 py-4 text-right">
                        {canEditEmployees ? (
                          <div className="flex justify-end gap-2">
                            <Button
                              type="button"
                              variant="secondary"
                              size="sm"
                              className="h-8"
                              onClick={(event) => {
                                event.stopPropagation();
                                setEditingEmployee(e);
                                setModalOpen(true);
                              }}
                            >
                              <PenSquare className="h-3.5 w-3.5" />
                              Edit
                            </Button>
                            <Button
                              type="button"
                              variant="destructive"
                              size="sm"
                              className="h-8"
                              onClick={(event) => {
                                event.stopPropagation();
                                setOffboardTarget(e);
                              }}
                            >
                              <UserMinus className="h-3.5 w-3.5" />
                              Offboard
                            </Button>
                          </div>
                        ) : (
                          <span className="text-xs text-ink-muted">View only</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}
    </div>
  );
}
