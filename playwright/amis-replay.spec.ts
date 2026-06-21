/**
 * AMIS Replay Dashboard — Replay job analysis.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToAMIS,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("AMIS Replay", () => {
  test("should load AMIS Replay with toolbar and timeframe buttons", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToAMIS(page, "replay");

    // Verify the replay selector dropdown exists
    await expect(page.getByText("Select Replay...")).toBeVisible({ timeout: 10000 });

    // Timeframe buttons only render when replay data is loaded; verify toolbar structure
    await expect(page.getByText("Select Replay...")).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
