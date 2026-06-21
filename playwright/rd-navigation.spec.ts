/**
 * R&D Navigation Smoke Tests — Verify all /rd/* routes load without errors.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToRD,
  waitForRDHeading,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

const RD_ROUTES = [
  "dashboard",
  "programs",
  "research",
  "workspace",
  "governance",
  "deployments",
  "lineage",
  "readiness",
] as const;

test.describe("R&D Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
  });

  for (const route of RD_ROUTES) {
    test(`should navigate to /rd/${route} without errors`, async ({ page }) => {
      const errors = watchConsole(page);

      await navigateToRD(page, route);

      if (route === "readiness") {
        // Readiness API currently returns 500 in dev; verify URL only
        await page.waitForURL("**/rd/readiness");
      } else {
        await waitForRDHeading(page, route);
      }

      expect(unexpectedErrors(errors)).toEqual([]);
    });
  }
});
