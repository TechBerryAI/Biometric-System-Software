import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Attendance } from "@/features/attendance/pages/AttendancePage";
import { API_BASE_URL } from "@/config/api";
import { renderWithProviders } from "@test/setup/render";
import { server } from "@test/msw/server";

const base = API_BASE_URL.replace(/\/$/, "");

const multiDaySummary = [
  {
    summary_date: "2024-06-01",
    employee_id: 1,
    device_user_id: "1001",
    employee_name: "Ada Lovelace",
    first_check_in: "2024-06-01T08:00:00Z",
    last_check_out: "2024-06-01T17:00:00Z",
    total_work_minutes: 480,
    sessions_count: 1,
  },
  {
    summary_date: "2024-06-01",
    employee_id: 2,
    device_user_id: "1002",
    employee_name: "Grace Hopper",
    first_check_in: "2024-06-01T10:00:00Z",
    last_check_out: "2024-06-01T18:00:00Z",
    total_work_minutes: 420,
    sessions_count: 1,
  },
  {
    summary_date: "2024-06-01",
    employee_id: 3,
    device_user_id: "1003",
    employee_name: "Zoe Absent",
    first_check_in: null,
    last_check_out: null,
    total_work_minutes: null,
    sessions_count: 0,
  },
];

describe("FE-UNIT-ATT-001 Attendance page", () => {
  it("renders attendance heading", async () => {
    renderWithProviders(<Attendance />, { withAuth: false, route: "/attendance" });
    expect(screen.getByRole("heading", { name: /attendance/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Ada Lovelace/i)).toBeInTheDocument();
    });
  });

  it("sorts late first and pins absents last", async () => {
    server.use(
      http.get(`${base}/attendance/daily-summary`, async () => {
        return HttpResponse.json(multiDaySummary);
      })
    );

    const user = userEvent.setup();
    renderWithProviders(<Attendance />, { withAuth: false, route: "/attendance" });

    await waitFor(() => {
      expect(screen.getByText("Grace Hopper")).toBeInTheDocument();
    });

    const rows = () =>
      within(screen.getByRole("table")).getAllByRole("row").slice(1).map((row) => {
        const nameCell = within(row).getAllByRole("cell")[1];
        return nameCell.querySelector("p")?.textContent ?? "";
      });

    expect(rows()).toEqual(["Ada Lovelace", "Grace Hopper", "Zoe Absent"]);

    await user.click(screen.getByRole("button", { name: /sort:/i }));
    await user.click(await screen.findByRole("menuitemradio", { name: /late first/i }));

    await waitFor(() => {
      expect(rows()).toEqual(["Grace Hopper", "Ada Lovelace", "Zoe Absent"]);
    });
  });
});
