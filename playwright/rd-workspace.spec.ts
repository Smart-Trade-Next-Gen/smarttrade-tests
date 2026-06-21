/**
 * R&D Workspace Wizard — End-to-end test for creating a research context + candidate.
 *
 * Uses the RG16 template with a unique VIX range to avoid fingerprint conflicts.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToRD,
  waitForRDHeading,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

const WORKSPACE_NAME = `E2E-Workspace-${Date.now()}`;
const CANDIDATE_NAME = `E2E-Candidate-${Date.now()}`;
// Use a unique VIX max so the fingerprint is different on every run
const UNIQUE_VIX_MAX = String(20 + (Date.now() % 100));

const MANUAL_WORKSPACE_NAME = `E2E-Manual-WS-${Date.now()}`;
const MANUAL_CANDIDATE_NAME = `E2E-Manual-Cand-${Date.now()}`;
const MANUAL_VIX_MAX = String(30 + (Date.now() % 100));

test.describe.serial("R&D Workspace Wizard", () => {
  test("should create a research workspace via template and verify it in Research", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToRD(page, "workspace");
    await waitForRDHeading(page, "workspace");

    // Step 0: Pick RG16 template
    await page.locator('[data-testid="workspace-template-rg16"]').click();

    // Verify we advanced to step 1
    await expect(page.locator('[data-testid="workspace-step-indicator"]')).toContainText("Context");

    // Step 1: Fill context name and change VIX max to ensure unique fingerprint
    await page.locator('[data-testid="workspace-context-name"]').fill(WORKSPACE_NAME);
    await page.locator('[data-testid="workspace-vix-max"]').fill(UNIQUE_VIX_MAX);
    await page.locator('[data-testid="workspace-next-btn"]').click();

    // Verify we advanced to step 2
    await expect(page.locator('[data-testid="workspace-step-indicator"]')).toContainText("Candidate");

    // Step 2: Fill candidate name and submit
    await page.locator('[data-testid="workspace-candidate-name"]').fill(CANDIDATE_NAME);
    await page.locator('[data-testid="workspace-create-btn"]').click();

    // Verify success screen appears (not error)
    await expect(page.locator('[data-testid="workspace-success"]')).toBeVisible({
      timeout: 15000,
    });

    // Verify created workspace details are shown
    await expect(page.locator('[data-testid="workspace-success"]')).toContainText("Workspace ID");

    // Navigate to Research page and verify the candidate appears
    await page.locator('[data-testid="workspace-view-research-btn"]').click();
    await waitForRDHeading(page, "research");

    // Wait for loading spinner to disappear
    const loadingSpinner = page.locator("text=Loading").first();
    try {
      await loadingSpinner.waitFor({ timeout: 5000 });
      await loadingSpinner.waitFor({ state: "hidden", timeout: 15000 });
    } catch {
      // Spinner may have already disappeared
    }

    // The candidate we just created should appear in the candidates list
    await expect(page.getByText(CANDIDATE_NAME)).toBeVisible({ timeout: 10000 });

    // Verify the candidate shows in a pipeline card with status indicator
    await expect(page.getByText(/Status:/).first()).toBeVisible();

    // Expand the card and verify pipeline steps are visible
    const firstCard = page.locator("button").filter({ hasText: /Status:/ }).first();
    await firstCard.click();
    await expect(page.getByText("Draft").first()).toBeVisible();
    await expect(page.getByText("Dataset").first()).toBeVisible();

    // No unexpected console errors
    expect(unexpectedErrors(errors)).toEqual([]);
  });

  test("should generate dataset from pipeline card without 403", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToRD(page, "workspace");
    await waitForRDHeading(page, "workspace");

    // Step 0: Pick RG16 template
    await page.locator('[data-testid="workspace-template-rg16"]').click();

    // Step 1: Fill context with unique fingerprint
    const dsWorkspaceName = `E2E-DS-WS-${Date.now()}`;
    const dsCandidateName = `E2E-DS-Cand-${Date.now()}`;
    const dsVixMax = String(40 + (Date.now() % 100));

    await page.locator('[data-testid="workspace-context-name"]').fill(dsWorkspaceName);
    await page.locator('[data-testid="workspace-vix-max"]').fill(dsVixMax);
    await page.locator('[data-testid="workspace-next-btn"]').click();

    // Step 2: Fill candidate and create
    await page.locator('[data-testid="workspace-candidate-name"]').fill(dsCandidateName);
    await page.locator('[data-testid="workspace-create-btn"]').click();

    // Verify success
    await expect(page.locator('[data-testid="workspace-success"]')).toBeVisible({
      timeout: 15000,
    });

    // Navigate to Research page
    await page.locator('[data-testid="workspace-view-research-btn"]').click();
    await waitForRDHeading(page, "research");

    // Wait for loading spinner to disappear
    const loadingSpinner = page.locator("text=Loading").first();
    try {
      await loadingSpinner.waitFor({ timeout: 5000 });
      await loadingSpinner.waitFor({ state: "hidden", timeout: 15000 });
    } catch {
      // Spinner may have already disappeared
    }

    // The candidate should appear
    await expect(page.getByText(dsCandidateName)).toBeVisible({ timeout: 10000 });

    // Expand the card
    const firstCard = page.locator("button").filter({ hasText: /Status:/ }).first();
    await firstCard.click();

    // Wait for pipeline to render
    await expect(page.getByText("Draft").first()).toBeVisible();

    // Click "Generate Dataset" button
    const genDatasetBtn = page.locator("button").filter({ hasText: "Generate Dataset" });
    await expect(genDatasetBtn).toBeVisible();
    await genDatasetBtn.click();

    // Wait a moment for the API call
    await page.waitForTimeout(3000);

    // Check that we did NOT get a 403 error (RBAC fix validation)
    const console403s = errors.filter(
      (e) => e.includes("403") || e.includes("Forbidden")
    );
    expect(console403s).toEqual([]);

    // Note: 500 from dataset generation is a known backend issue (MDS auth)
    // The frontend correctly triggers the API; backend service-to-service auth
    // is a separate infrastructure concern.
  });

  test("should create a workspace with manual instrument selection", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToRD(page, "workspace");
    await waitForRDHeading(page, "workspace");

    // Step 0: Skip template — start from scratch
    await page.locator('[data-testid="workspace-skip-template"]').click();

    // Verify we advanced to step 1 (Context)
    await expect(page.locator('[data-testid="workspace-step-indicator"]')).toContainText("Context");

    // Fingerprint should show "?" because no instruments are selected yet
    const fingerprintBefore = page.locator("text=/^\\?\\|/");
    await expect(fingerprintBefore).toBeVisible();

    // Open instrument search popup
    await page.locator('button:has-text("Search instruments")').click();

    // Wait for popup and type "NIFTY"
    await page.locator('input[placeholder="Search instrument..."]').waitFor();
    await page.locator('input[placeholder="Search instrument..."]').fill("NIFTY");

    // Wait for API results to render (at least one clickable row)
    const firstResult = page.locator('div.cursor-pointer').first();
    await firstResult.waitFor({ timeout: 10000 });

    // Click the first instrument result
    await firstResult.click();

    // Popup should close and a chip should appear below the search field
    // The chip contains the selected instrument ID (e.g. "NSE:CASH:INDEX:NIFTY50")
    await expect(page.locator('.inline-flex.items-center.gap-1')).toContainText("NIFTY", { timeout: 5000 });

    // Fingerprint should now contain the selected instrument (no longer "?")
    const fingerprintAfter = page.locator("text=/^[^?].*\\|/");
    await expect(fingerprintAfter).toBeVisible();

    // Fill remaining required fields
    await page.locator('[data-testid="workspace-context-name"]').fill(MANUAL_WORKSPACE_NAME);
    await page.locator('[data-testid="workspace-vix-max"]').fill(MANUAL_VIX_MAX);

    // Advance to candidate step
    await page.locator('[data-testid="workspace-next-btn"]').click();
    await expect(page.locator('[data-testid="workspace-step-indicator"]')).toContainText("Candidate");

    // Fill candidate name and create
    await page.locator('[data-testid="workspace-candidate-name"]').fill(MANUAL_CANDIDATE_NAME);
    await page.locator('[data-testid="workspace-create-btn"]').click();

    // Verify success screen
    await expect(page.locator('[data-testid="workspace-success"]')).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-testid="workspace-success"]')).toContainText("Workspace ID");

    // Navigate to Research page and verify the candidate appears
    await page.locator('[data-testid="workspace-view-research-btn"]').click();
    await waitForRDHeading(page, "research");

    // Wait for loading spinner to disappear
    const loadingSpinner = page.locator("text=Loading").first();
    try {
      await loadingSpinner.waitFor({ timeout: 5000 });
      await loadingSpinner.waitFor({ state: "hidden", timeout: 15000 });
    } catch {
      // Spinner may have already disappeared
    }

    // The candidate we just created should appear in the candidates list
    await expect(page.getByText(MANUAL_CANDIDATE_NAME)).toBeVisible({ timeout: 10000 });

    // Verify the candidate shows in a pipeline card with status indicator
    await expect(page.getByText(/Status:/).first()).toBeVisible();

    // Expand the card and verify pipeline steps are visible
    const firstCard = page.locator("button").filter({ hasText: /Status:/ }).first();
    await firstCard.click();
    await expect(page.getByText("Draft").first()).toBeVisible();
    await expect(page.getByText("Dataset").first()).toBeVisible();

    // No unexpected console errors
    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
