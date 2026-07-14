import { expect, test } from "@playwright/test";
import { annotateTestId } from "../helpers/annotations";
import { loginAs, skipIfStackUnavailable } from "../helpers/auth";

test.describe("E2E-OPS-001 Operations queue", () => {
  test.beforeAll(async () => {
    await skipIfStackUnavailable();
  });

  test("Operations Center shows metrics and device command queue", async ({ page }) => {
    annotateTestId("E2E-OPS-001");

    await loginAs(page);
    await page.getByRole("link", { name: "Operations" }).click();
    await expect(page.getByRole("heading", { name: "Operations Center" })).toBeVisible();
    await expect(page.getByText("Queue depth")).toBeVisible();
    await expect(page.getByText("Stale commands")).toBeVisible();
    await expect(page.getByText("Dead letters")).toBeVisible();
    await expect(page.getByText("Failing devices")).toBeVisible();
    await expect(page.getByText("Device Command Queue")).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Command" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Status" })).toBeVisible();
  });
});
