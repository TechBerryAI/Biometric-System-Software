import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OffboardEmployeeDialog } from "@/features/employees/components/OffboardEmployeeDialog";
import { renderWithProviders } from "@test/setup/render";

describe("FE-UNIT-EMP-FORM-002 OffboardEmployeeDialog", () => {
  it("shows employee identity and confirms offboard", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const onOpenChange = vi.fn();

    renderWithProviders(
      <OffboardEmployeeDialog
        open
        onOpenChange={onOpenChange}
        employeeName="Ada Lovelace"
        deviceUserId="1001"
        onConfirm={onConfirm}
      />,
      { withAuth: false },
    );

    expect(screen.getByRole("heading", { name: /offboard employee/i })).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("1001")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^offboard$/i }));
    expect(onConfirm).toHaveBeenCalled();
  });
});
