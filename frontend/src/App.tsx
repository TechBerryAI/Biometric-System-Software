import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "@/auth/RequireAuth";
import { AppLayout } from "@/components/layout/AppLayout";
import { Attendance } from "@/pages/Attendance";
import { Dashboard } from "@/pages/Dashboard";
import { EmployeeProfile } from "@/pages/EmployeeProfile";
import { Employees } from "@/pages/Employees";
import { Login } from "@/pages/Login";
import { Operations } from "@/pages/Operations";
import { Profile } from "@/pages/Profile";
import { Reports } from "@/pages/Reports";
import { Settings } from "@/pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <AppLayout>
              <Routes>
                <Route
                  path="/"
                  element={
                    <RequireAuth permission="reports:read">
                      <Dashboard />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/employees"
                  element={
                    <RequireAuth permission="employee:view">
                      <Employees />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/employees/:employeeId"
                  element={
                    <RequireAuth permission="employee:view">
                      <EmployeeProfile />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/attendance"
                  element={
                    <RequireAuth permission="reports:read">
                      <Attendance />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/reports"
                  element={
                    <RequireAuth permission="anomaly:manage">
                      <Reports />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/operations"
                  element={
                    <RequireAuth permission="metrics:read">
                      <Operations />
                    </RequireAuth>
                  }
                />
                <Route
                  path="/profile"
                  element={<Profile />}
                />
                <Route
                  path="/settings"
                  element={
                    <RequireAuth permission="metrics:read">
                      <Settings />
                    </RequireAuth>
                  }
                />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </AppLayout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
