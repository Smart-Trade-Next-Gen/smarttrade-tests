/**
 * R&D Deployments — Production deployment status and context compatibility.
 */

import { test, expect } from "@playwright/test";
import {
  loginAndWait,
  navigateToRD,
  waitForRDHeading,
  watchConsole,
  unexpectedErrors,
} from "./helpers/rd-helpers";

test.describe("R&D Deployments", () => {
  test("should load Deployments page with structure", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);
    await navigateToRD(page, "deployments");
    await waitForRDHeading(page, "deployments");

    await expect(page.getByTestId("rd-deployments-heading")).toBeVisible();
    await expect(
      page.getByText("Promote artifacts to PRODUCTION status via Governance to enable deployment")
        .or(page.locator("table"))
    ).toBeVisible();

    expect(unexpectedErrors(errors)).toEqual([]);
  });
});
