/**
 * R&D Dashboard — Structural and empty-state assertions.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToRD,
  waitForRDHeading,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("R&D Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
    await navigateToRD(page, "dashboard");
    await waitForRDHeading(page, "dashboard");
  });

  test("should show dashboard structure (KPIs, queue, decisions, incidents)", async ({ page }) => {
    const errors = watchConsole(page);

    // Verify key sections exist
    await expect(page.getByText("Dependency Health")).toBeVisible();
    await expect(page.getByText("Promotion Queue")).toBeVisible();
    await expect(page.getByText("Recent Decisions")).toBeVisible();
    await expect(page.getByText("Open Incidents")).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });

  test("should render dependency health table or empty state", async ({ page }) => {
    const errors = watchConsole(page);

    const healthTable = page.locator("table").filter({ has: page.locator("th", { hasText: "Dependency" }) });
    const emptyState = page.getByText("No dependencies configured");

    // Either the table or an empty-state message should be present
    await expect(healthTable.or(emptyState)).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
