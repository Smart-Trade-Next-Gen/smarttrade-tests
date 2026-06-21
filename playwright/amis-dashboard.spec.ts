/**
 * AMIS Research Dashboard — Trade intelligence overview.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToAMIS,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("AMIS Dashboard — Trade Intelligence (amis-lab-service)", () => {
  test("should load AMIS Research Dashboard", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToAMIS(page, "replay");

    // AMIS Replay doesn't have a dedicated heading; verify toolbar
    await expect(page.getByText("Select Replay...")).toBeVisible({ timeout: 10000 });

    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
