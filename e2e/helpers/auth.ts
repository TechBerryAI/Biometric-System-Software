import { type Page, expect, test } from "@playwright/test";

export const DEFAULT_E2E_EMAIL = process.env.E2E_ADMIN_EMAIL || "admin@example.com";
export const DEFAULT_E2E_PASSWORD = process.env.E2E_ADMIN_PASSWORD || "Admin123!";

export function e2eBaseURL(): string {
  return process.env.E2E_BASE_URL || "http://localhost:5173";
}

/**
 * Skip the suite when E2E_SKIP=1 or the login page is unreachable.
 * Call from test.beforeAll so discovery (`--list`) still enumerates tests.
 */
export async function skipIfStackUnavailable(): Promise<void> {
  if (process.env.E2E_SKIP === "1") {
    test.skip(true, "E2E_SKIP=1");
    return;
  }

  const loginURL = `${e2eBaseURL().replace(/\/$/, "")}/login`;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3_000);
    const res = await fetch(loginURL, { signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) {
      test.skip(true, `Login page not reachable (${res.status}) at ${loginURL}`);
    }
  } catch {
    test.skip(true, `Login page not reachable at ${loginURL}`);
  }
}

/** Fill email/password on /login and submit Sign in. */
export async function loginAs(
  page: Page,
  email: string = DEFAULT_E2E_EMAIL,
  password: string = DEFAULT_E2E_PASSWORD,
): Promise<void> {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByPlaceholder("admin@company.com").fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

export async function signOut(page: Page): Promise<void> {
  // TopBar account trigger shows role label (e.g. "Super Admin") or email on large screens.
  await page
    .locator("header button")
    .filter({ hasText: /Super Admin|GOD mode|CEO|IT Admin|HR Admin|@/ })
    .first()
    .click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
}
