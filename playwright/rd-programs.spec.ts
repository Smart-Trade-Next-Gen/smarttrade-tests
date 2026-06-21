/**
 * R&D Programs Page — Research programs and tracks.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToRD,
  waitForRDHeading,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("R&D Programs", () => {
  test("should load Programs page with structure", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToRD(page, "programs");
    await waitForRDHeading(page, "programs");

    await expect(page.getByTestId("rd-programs-heading")).toBeVisible();
    await expect(
      page.getByText("No research programs found")
        .or(page.locator("table"))
    ).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
