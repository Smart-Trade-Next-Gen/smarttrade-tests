/**
 * R&D Smoke Test — Validates login baseline and R&D page accessibility.
 *
 * Must pass before any other R&D Playwright tests are written.
 */

import { test, expect, Page } from "@playwright/test";

const BASE_URL = "http://localhost:3000";
const TEST_USERNAME = "test_pie_e2e";
const TEST_PASSWORD = "Test123.e2e";

/**
 * Helper: Login and handle account selection modal.
 */
async function loginAndWait(page: Page) {
  await page.goto(BASE_URL);

  // Wait for login form
  await page.locator('input[placeholder="Enter your username"]').waitFor({ timeout: 15000 });
  await page.locator('input[placeholder="Enter your username"]').fill(TEST_USERNAME);
  await page.locator('input[placeholder="Enter your password"]').fill(TEST_PASSWORD);
  await page.locator("button").filter({ hasText: /^Login$/ }).click();

  // Handle account selection modal (BrokerSelectionModal)
  const accountModal = page.locator("text=Select Trading Account");
  try {
    await accountModal.waitFor({ timeout: 8000 });
    await page.locator("button").filter({ hasText: "TEST_E2E" }).click();
    await accountModal.waitFor({ state: "hidden", timeout: 8000 });
  } catch {
    // Modal didn't appear — account already selected from localStorage
  }

  // Wait for dashboard content to confirm trading UI has mounted
  await page.getByText("Total portfolio value").waitFor({ timeout: 10000 });
}

/**
 * Collect console errors during the test.
 * Filters out expected dev-environment noise (WS failures, 404 health checks, etc.).
 */
function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      errors.push(msg.text());
    }
  });
  return errors;
}

function isExpectedError(text: string): boolean {
  const expectedPatterns = [
    "favicon",
    "WebSocket",
    "WS",
    "broker connection",
    "BrokerConnectionHealth",
    "notification",
    "UserEvent WS",
    "404 (Not Found)",
    "401 (Unauthorized)",
    "403 (Forbidden)",
    "Expected moveto path command",
  ];
  return expectedPatterns.some((p) => text.includes(p));
}

test.describe("R&D Smoke Test", () => {
  test("should login and reach the R&D Dashboard", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);

    // Navigate to R&D Dashboard via sidebar
    await page.locator('[data-testid="nav-rd-dashboard"]').click();

    // Verify R&D Dashboard heading is visible
    await expect(page.locator('[data-testid="rd-dashboard-heading"]')).toBeVisible({
      timeout: 10000,
    });

    // No unexpected console errors (allow WS/404/401 dev-environment noise)
    const unexpectedErrors = errors.filter((e) => !isExpectedError(e));
    expect(unexpectedErrors).toEqual([]);
  });

  test("should navigate to Research page from sidebar", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);

    await page.locator('[data-testid="nav-rd-research"]').click();
    await expect(page.locator('[data-testid="rd-research-heading"]')).toBeVisible({
      timeout: 10000,
    });

    const unexpectedErrors = errors.filter((e) => !isExpectedError(e));
    expect(unexpectedErrors).toEqual([]);
  });

  test("should navigate to Governance page from sidebar", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);

    await page.locator('[data-testid="nav-rd-governance"]').click();
    await expect(page.locator('[data-testid="rd-governance-heading"]')).toBeVisible({
      timeout: 10000,
    });

    const unexpectedErrors = errors.filter((e) => !isExpectedError(e));
    expect(unexpectedErrors).toEqual([]);
  });

  test("should navigate to Workspace page from sidebar", async ({ page }) => {
    const errors = watchConsole(page);

    await loginAndWait(page);

    await page.locator('[data-testid="nav-rd-workspace"]').click();
    await expect(page.locator('[data-testid="rd-workspace-heading"]')).toBeVisible({
      timeout: 10000,
    });

    const unexpectedErrors = errors.filter((e) => !isExpectedError(e));
    expect(unexpectedErrors).toEqual([]);
  });
});
