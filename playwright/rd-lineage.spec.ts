/**
 * R&D Lineage — Artifact provenance and dependency tracing.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToRD,
  waitForRDHeading,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("R&D Lineage", () => {
  test("should load Lineage page with structural elements", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToRD(page, "lineage");
    await page.locator('[data-testid="rd-lineage-heading"]').waitFor({ timeout: 20000 });

    await expect(page.getByTestId("rd-lineage-heading")).toBeVisible();

    // Empty state or lineage content (Upstream/Downstream buttons exist when page loads)
    const lineageContent =
      page.getByText("No lineage edges found for this artifact")
        .or(page.locator("button", { hasText: "Upstream" }))
        .or(page.locator("button", { hasText: "Downstream" }));
    await expect(lineageContent.first()).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
