import { api } from "@/shared/api/client";
import type {
  Employee,
  EmployeeCreatePayload,
  EmployeeDailyAttendance,
  EmployeeDetail,
} from "@/types";

export async function fetchEmployees(): Promise<Employee[]> {
  const { data } = await api.get<Employee[]>("/employees");
  return data;
}

export async function upsertEmployee(payload: EmployeeCreatePayload): Promise<Employee> {
  const { data } = await api.post<Employee>("/employees", payload);
  return data;
}

export async function updateEmployee(employeeId: number, payload: EmployeeCreatePayload): Promise<Employee> {
  const { data } = await api.put<Employee>(`/employees/${employeeId}`, payload);
  return data;
}

export async function offboardEmployee(employeeId: number): Promise<void> {
  await api.delete(`/employees/${employeeId}`);
}

export async function fetchEmployeeById(employeeId: number): Promise<EmployeeDetail> {
  const { data } = await api.get<EmployeeDetail>(`/employees/${employeeId}`);
  return data;
}

export async function fetchEmployeeDailyAttendance(
  employeeId: number,
  params: { from?: string; to?: string }
): Promise<EmployeeDailyAttendance[]> {
  const { data } = await api.get<EmployeeDailyAttendance[]>(
    `/employees/${employeeId}/daily-attendance`,
    { params }
  );
  return data;
}
