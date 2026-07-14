import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import {
  AttendanceAdjustmentModal,
  AttendanceRowEditButton,
} from "@/features/attendance/components/AttendanceAdjustmentPanel";
import { renderWithProviders } from "@test/setup/render";

const useAuthMock = vi.fn();

vi.mock("@/features/auth/AuthContext", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => useAuthMock(),
}));

describe("FE-UNIT-ADJ-001 AttendanceAdjustmentPanel", () => {
  it("renders edit button and gated modal when capability present", async () => {
    useAuthMock.mockReturnValue({
      user: {
        user_uuid: "1",
        email: "admin@company.com",
        role: "SUPER_ADMIN",
        active: true,
        capabilities: { attendance_adjust: true, forensic_audit: true },
      },
      loading: false,
      can: () => true,
      login: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
      applyAuthTokens: vi.fn(),
    });

    const { unmount } = renderWithProviders(
      <AttendanceRowEditButton onClick={() => undefined} />,
      { withAuth: false },
    );
    expect(screen.getByRole("button", { name: /edit attendance/i })).toBeInTheDocument();
    unmount();

    renderWithProviders(
      <AttendanceAdjustmentModal
        open
        onOpenChange={() => undefined}
        employeeId={1}
        row={{
          summary_date: "2024-06-01",
          first_check_in: "2024-06-01T09:00:00Z",
          last_check_out: "2024-06-01T17:00:00Z",
          total_work_minutes: 480,
          absent: false,
          punch_count: 2,
        }}
        onApplied={() => undefined}
      />,
      { withAuth: false },
    );

    expect(await screen.findByRole("heading", { name: /edit attendance/i })).toBeInTheDocument();
  });

  it("returns null modal when capability missing", () => {
    useAuthMock.mockReturnValue({
      user: {
        user_uuid: "1",
        email: "viewer@company.com",
        role: "CEO",
        active: true,
        capabilities: { attendance_adjust: false, forensic_audit: false },
      },
      loading: false,
      can: () => false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
      applyAuthTokens: vi.fn(),
    });

    const { container } = renderWithProviders(
      <AttendanceAdjustmentModal
        open
        onOpenChange={() => undefined}
        employeeId={1}
        row={{
          summary_date: "2024-06-01",
          first_check_in: null,
          last_check_out: null,
          total_work_minutes: null,
          absent: true,
          punch_count: 0,
        }}
        onApplied={() => undefined}
      />,
      { withAuth: false },
    );

    expect(container).toBeEmptyDOMElement();
  });
});
