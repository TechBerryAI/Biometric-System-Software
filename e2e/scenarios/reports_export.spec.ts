import { expect, test } from "@playwright/test";
import { annotateTestId } from "../helpers/annotations";
import { loginAs, skipIfStackUnavailable } from "../helpers/auth";

test.describe("E2E-EXP-001 Report exports", () => {
  test.beforeAll(async () => {
    await skipIfStackUnavailable();
  });

  test("Reports page opens format dialog with PDF / Word / Excel", async ({ page }) => {
    annotateTestId("E2E-EXP-001");

    await loginAs(page);
    await page.getByRole("link", { name: "Reports" }).click();
    await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
    await expect(page.getByText("Report export")).toBeVisible();
    await expect(page.getByText("Window")).toBeVisible();

    await page.getByRole("button", { name: "Download" }).click();
    await expect(page.getByRole("heading", { name: "Download attendance report" })).toBeVisible();
    await expect(page.getByRole("button", { name: /PDF/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Word/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Excel/ })).toBeVisible();
  });
});
