/**
 * R&D Readiness — Candidate readiness assessment.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToRD,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("R&D Readiness", () => {
  test("should navigate to Readiness page without console errors", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToRD(page, "readiness");

    // Verify URL changed (page mounted and began loading)
    await page.waitForURL("**/rd/readiness");

    // Readiness API currently returns 500 in dev environment.
    // We verify the page renders without crashing (no unexpected console errors).
    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
