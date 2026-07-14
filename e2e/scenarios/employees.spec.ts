import { expect, test } from "@playwright/test";
import { annotateTestId } from "../helpers/annotations";
import { loginAs, skipIfStackUnavailable } from "../helpers/auth";

test.describe("E2E-EMP-001 Employees directory + add modal", () => {
  test.beforeAll(async () => {
    await skipIfStackUnavailable();
  });

  test("opens Employees, Add employee modal, and can create a directory row", async ({ page }) => {
    annotateTestId("E2E-EMP-001");

    await loginAs(page);
    await page.getByRole("link", { name: "Employees" }).click();
    await expect(page.getByRole("heading", { name: "Employees" })).toBeVisible();
    await expect(page.getByText(/device_user_id/)).toBeVisible();

    const addBtn = page.getByRole("button", { name: "Add employee" });
    await expect(addBtn).toBeVisible();
    await addBtn.click();

    await expect(page.getByRole("heading", { name: "Add employee" })).toBeVisible();
    await expect(page.getByPlaceholder("Terminal user id")).toBeVisible();
    await expect(page.getByPlaceholder("Full name")).toBeVisible();

    const suffix = Date.now().toString().slice(-6);
    const deviceUserId = `E2E${suffix}`;
    const displayName = `E2E Employee ${suffix}`;

    await page.getByPlaceholder("Terminal user id").fill(deviceUserId);
    await page.getByPlaceholder("Full name").fill(displayName);
    await page.locator("select").first().selectOption("Operations");
    await page.getByRole("button", { name: "Create employee" }).click();

    await expect(page.getByRole("heading", { name: "Add employee" })).toBeHidden({ timeout: 20_000 });
    await expect(page.getByText(displayName)).toBeVisible({ timeout: 20_000 });
  });
});
