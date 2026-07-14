import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { AddEmployeeModal } from "@/features/employees/components/AddEmployeeModal";
import { renderWithProviders } from "@test/setup/render";

describe("FE-UNIT-EMP-FORM-001 AddEmployeeModal", () => {
  it("renders department and shift fields", () => {
    renderWithProviders(
      <AddEmployeeModal open onOpenChange={() => undefined} />,
      { withAuth: false },
    );

    expect(screen.getByRole("heading", { name: /add employee/i })).toBeInTheDocument();
    expect(screen.getByText("Department")).toBeInTheDocument();
    expect(screen.getByText("Shift start")).toBeInTheDocument();
    expect(screen.getByText("Shift end")).toBeInTheDocument();
  });
});
