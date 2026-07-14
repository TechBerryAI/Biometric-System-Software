import { expect, test } from "@playwright/test";
import { annotateTestId } from "../helpers/annotations";
import { loginAs, skipIfStackUnavailable } from "../helpers/auth";

test.describe("E2E-ATT-001 Sync + attendance workflow", () => {
  test.beforeAll(async () => {
    await skipIfStackUnavailable();
  });

  test("Sync now and Attendance roster controls are reachable", async ({ page }) => {
    annotateTestId("E2E-ATT-001");

    await loginAs(page);

    await expect(page.getByRole("button", { name: "Sync now" })).toBeVisible();
    await page.getByRole("button", { name: "Sync now" }).click();
    // Sync may succeed or warn depending on device connectivity; UI should respond.
    await expect(
      page.locator("aside").getByText(/Synced|Sync failed|check device|Manual sync|Healthy|Ready|Degraded|Offline/i),
    ).toBeVisible({ timeout: 30_000 });

    await page.getByRole("link", { name: "Attendance" }).click();
    await expect(page.getByRole("heading", { name: "Attendance" })).toBeVisible();
    await expect(page.getByText(/Sync now/)).toBeVisible();
    await expect(page.getByText("Present")).toBeVisible();
    await expect(page.getByText("Absent")).toBeVisible();
    await expect(page.getByRole("button", { name: "Download" })).toBeVisible();
  });
});
