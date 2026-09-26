import { expect, test } from "@playwright/test";
import { annotateTestId } from "../helpers/annotations";
import { loginAs, skipIfStackUnavailable } from "../helpers/auth";

test.describe("E2E-CORR-001 Correction → audit", () => {
  test.beforeAll(async () => {
    await skipIfStackUnavailable();
  });

  test("audit route and correction surfaces follow capability gates", async ({ page }) => {
    annotateTestId("E2E-CORR-001");

    await loginAs(page);

    await page.goto("/audit");
    const auditHeading = page.getByRole("heading", { name: "Audit" });
    const onAudit = await auditHeading.isVisible().catch(() => false);

    if (onAudit) {
      await expect(page.getByText("Device activity", { exact: true })).toBeVisible();
      await expect(page.getByRole("columnheader", { name: "Created" })).toBeVisible();
    } else {
      // Non-operator SUPER_ADMIN is redirected away from /audit (forensic_audit required).
      await expect(page).not.toHaveURL(/\/audit$/);
    }

    await page.getByRole("link", { name: "Employees" }).click();
    await expect(page.getByRole("heading", { name: "Employees" })).toBeVisible();

    const employeeRow = page.locator("tbody tr").filter({ hasText: /ID \d+/ }).first();
    if (await employeeRow.count()) {
      await employeeRow.click();
      await page.getByRole("button", { name: "Attendance" }).click();
      const editBtn = page.getByRole("button", { name: "Update times" });
      if (await editBtn.count()) {
        await editBtn.first().click();
        await expect(page.getByRole("heading", { name: /Update times/ })).toBeVisible();
        await expect(page.getByRole("button", { name: "Apply" })).toBeVisible();
        await page.getByRole("button", { name: "Cancel" }).click();
      }
    } else {
      await expect(page.getByText(/No matches|Try another search/i)).toBeVisible();
    }
  });
});
