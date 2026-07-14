import { test } from "@playwright/test";

/** Record a stable matrix test ID on the current Playwright test. */
export function annotateTestId(testId: string): void {
  test.info().annotations.push({ type: "testid", description: testId });
}
