/**
 * R&D Research Page — Candidates, contexts, experiments, and pipeline cards.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToRD,
  waitForRDHeading,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("R&D Research", () => {
  test.beforeEach(async ({ page }) => {
    await loginAndWait(page);
    await navigateToRD(page, "research");
    await waitForRDHeading(page, "research");
  });

  test("should show candidate tab with structural elements", async ({ page }) => {
    const errors = watchConsole(page);

    // Default tab is "candidates" (implemented as buttons, not role="tab")
    await expect(page.locator("button").filter({ hasText: "Candidates" })).toBeVisible();
    await expect(page.locator("button").filter({ hasText: "Experiments" })).toBeVisible();
    await expect(page.locator("button").filter({ hasText: "Assets" })).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });

  test("should switch tabs without errors", async ({ page }) => {
    const errors = watchConsole(page);

    await page.locator("button").filter({ hasText: "Experiments" }).click();
    await expect(page.getByText("Experiment tracking coming in next iteration")).toBeVisible();

    await page.locator("button").filter({ hasText: "Assets" }).click();
    await expect(page.getByText("Asset registry coming in next iteration")).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });

  test("should show candidate pipeline cards with context details", async ({ page }) => {
    const errors = watchConsole(page);

    // Wait for loading spinner to disappear
    const loadingSpinner = page.locator("text=Loading").first();
    try {
      await loadingSpinner.waitFor({ timeout: 5000 });
      await loadingSpinner.waitFor({ state: "hidden", timeout: 15000 });
    } catch {
      // Spinner may have already disappeared
    }

    // Candidate cards should exist (either with candidates or empty state)
    const emptyState = page.getByText("No candidates found");
    const hasCandidates = await emptyState.isVisible().catch(() => false);

    if (!hasCandidates) {
      // At least one candidate card should be visible
      const firstCard = page.locator("text=/Status:/").first();
      await expect(firstCard).toBeVisible();

      // Card should show status text
      await expect(page.getByText(/Status:/).first()).toBeVisible();
    }

    expect(unexpectedErrors(errors)).toEqual([]);
  });

  test("should expand candidate card and show pipeline visualization", async ({ page }) => {
    const errors = watchConsole(page);

    // Wait for loading spinner to disappear
    const loadingSpinner = page.locator("text=Loading").first();
    try {
      await loadingSpinner.waitFor({ timeout: 5000 });
      await loadingSpinner.waitFor({ state: "hidden", timeout: 15000 });
    } catch {
      // Spinner may have already disappeared
    }

    // Check if any candidates exist
    const emptyState = page.getByText("No candidates found");
    const isEmpty = await emptyState.isVisible().catch(() => false);

    if (isEmpty) {
      test.skip(true, "No candidates to test pipeline card");
      return;
    }

    // Click the first candidate card to expand it
    const firstCard = page.locator("button").filter({ hasText: /Status:/ }).first();
    await firstCard.click();

    // After expansion, pipeline steps should be visible
    // Check for pipeline step labels
    await expect(page.getByText("Draft").first()).toBeVisible();
    await expect(page.getByText("Dataset").first()).toBeVisible();
    await expect(page.getByText("Research").first()).toBeVisible();
    await expect(page.getByText("Validate").first()).toBeVisible();
    await expect(page.getByText("Shadow").first()).toBeVisible();
    await expect(page.getByText("Candidate").first()).toBeVisible();
    await expect(page.getByText("Live").first()).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
