import { expect, test } from "@playwright/test";
import { annotateTestId } from "../helpers/annotations";
import { loginAs, signOut, skipIfStackUnavailable } from "../helpers/auth";

test.describe("E2E-AUTH-001 Auth login / logout / forbidden", () => {
  test.beforeAll(async () => {
    await skipIfStackUnavailable();
  });

  test("login succeeds, protected routes redirect when logged out, sign out returns to login", async ({
    page,
  }) => {
    annotateTestId("E2E-AUTH-001");

    await page.goto("/employees");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

    await loginAs(page);
    await expect(page.getByText("Biometrica")).toBeVisible();
    await expect(page.getByRole("link", { name: "Employees" })).toBeVisible();

    await signOut(page);

    await page.goto("/attendance");
    await expect(page).toHaveURL(/\/login/);
  });

  test("wrong password shows login error", async ({ page }) => {
    annotateTestId("E2E-AUTH-001");

    await page.goto("/login");
    await page.getByPlaceholder("admin@company.com").fill("admin@example.com");
    await page.locator('input[type="password"]').fill("WrongPassword!");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.locator("p.text-destructive, p.text-xs.text-destructive").first()).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });
});
