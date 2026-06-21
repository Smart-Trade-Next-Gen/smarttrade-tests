/**
 * R&D Governance — Promotion queue, gate evaluation, and decision history.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToRD,
  waitForRDHeading,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("R&D Governance", () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
    await navigateToRD(page, "governance");
    await waitForRDHeading(page, "governance");
  });

  test("should show governance tabs and structural elements", async ({ page }) => {
    const errors = watchConsole(page);

    await expect(page.locator('[data-testid="governance-tab-queue"]')).toBeVisible();
    await expect(page.locator('[data-testid="governance-tab-history"]')).toBeVisible();
    await expect(page.locator('[data-testid="governance-tab-config"]')).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });

  test("should show empty promotion queue with correct messaging", async ({ page }) => {
    const errors = watchConsole(page);

    // Queue tab is active by default
    await expect(
      page.getByText("Queue is clear").or(page.locator('[data-testid="status-badge-under_review"]'))
    ).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });

  test("should show decision history or empty state", async ({ page }) => {
    const errors = watchConsole(page);

    await page.locator('[data-testid="governance-tab-history"]').click();

    // Empty state or table should be present (no h2 in history tab)
    await expect(
      page.getByText("No decisions recorded").or(page.locator("table"))
    ).toBeVisible({ timeout: 8000 });

    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
