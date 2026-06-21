/**
 * AMIS Training Datasets — Dataset management and generation.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToAMIS,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("AMIS Training Datasets — Dataset Registry (amis-lab-service)", () => {
  test("should load Training Datasets page with structure", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToAMIS(page, "training");

    // Verify page heading and create button
    await expect(page.getByText("Training Datasets")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Instrument pipelines:")).toBeVisible();

    // Dataset table or empty state should exist
    await expect(
      page.getByText("No datasets found").or(page.locator("table"))
    ).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
