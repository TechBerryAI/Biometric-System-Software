import { expect, test } from "@playwright/test";
import { annotateTestId } from "../helpers/annotations";
import { loginAs, skipIfStackUnavailable } from "../helpers/auth";

test.describe("E2E-DAY-001 Company day story", () => {
  test.beforeAll(async () => {
    await skipIfStackUnavailable();
  });

  test("login → employees → attendance → reports → operations", async ({ page }) => {
    annotateTestId("E2E-DAY-001");

    await loginAs(page);
    await expect(page.getByText("Biometrica")).toBeVisible();

    await page.getByRole("link", { name: "Employees" }).click();
    await expect(page.getByRole("heading", { name: "Employees" })).toBeVisible();

    const suffix = Date.now().toString().slice(-6);
    const deviceUserId = `DAY${suffix}`;
    const displayName = `Day Story ${suffix}`;

    await page.getByRole("button", { name: "Add employee" }).click();
    await page.getByPlaceholder("Terminal user id").fill(deviceUserId);
    await page.getByPlaceholder("Full name").fill(displayName);
    await page.getByRole("button", { name: "Create employee" }).click();
    await expect(page.getByText(displayName)).toBeVisible({ timeout: 20_000 });

    await page.getByRole("link", { name: "Attendance" }).click();
    await expect(page.getByRole("heading", { name: "Attendance" })).toBeVisible();
    await expect(page.getByText("In view")).toBeVisible();

    await page.getByRole("link", { name: "Reports" }).click();
    await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
    await expect(page.getByText("Report export")).toBeVisible();

    await page.getByRole("link", { name: "Operations" }).click();
    await expect(page.getByRole("heading", { name: "Operations Center" })).toBeVisible();
    await expect(page.getByText("Device Command Queue")).toBeVisible();
  });
});
