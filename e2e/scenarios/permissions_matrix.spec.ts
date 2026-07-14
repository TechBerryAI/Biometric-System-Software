import { expect, test } from "@playwright/test";
import { annotateTestId } from "../helpers/annotations";
import { loginAs, skipIfStackUnavailable } from "../helpers/auth";

const NAV_ITEMS = ["Dashboard", "Employees", "Attendance", "Reports", "Operations", "Settings"] as const;

test.describe("E2E-PERM-001 Permissions matrix", () => {
  test.beforeAll(async () => {
    await skipIfStackUnavailable();
  });

  test("bootstrap admin sees full sidebar; unauthenticated users are blocked", async ({ page }) => {
    annotateTestId("E2E-PERM-001");

    await page.goto("/operations");
    await expect(page).toHaveURL(/\/login/);

    await loginAs(page);

    for (const label of NAV_ITEMS) {
      await expect(page.getByRole("link", { name: label })).toBeVisible();
    }

    await page.getByRole("link", { name: "Settings" }).click();
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

    await page.getByRole("link", { name: "Employees" }).click();
    await expect(page.getByRole("button", { name: "Add employee" })).toBeVisible();
  });
});
