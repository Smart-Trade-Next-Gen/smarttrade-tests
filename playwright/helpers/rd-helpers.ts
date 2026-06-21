/**
 * R&D Playwright Test Helpers
 *
 * Shared utilities for logging in, navigating R&D pages, and verifying
 * page state. Used across all R&D spec files.
 */

import { Page } from "@playwright/test";

const TEST_USERNAME = "test_pie_e2e";
const TEST_PASSWORD = "Test123.e2e";

/**
 * Expected console error patterns in dev environment (WS, 404 health checks, etc.).
 */
const EXPECTED_ERROR_PATTERNS = [
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

/**
 * Start watching console errors. Returns an array that will be populated.
 */
export function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      errors.push(msg.text());
    }
  });
  return errors;
}

/**
 * Return only unexpected console errors (filter out dev-environment noise).
 */
export function unexpectedErrors(errors: string[]): string[] {
  return errors.filter((e) =>
    !EXPECTED_ERROR_PATTERNS.some((p) => e.includes(p))
  );
}

/**
 * Login via the SmartTrade login form and wait for the Dashboard to load.
 */
export async function loginAndWait(page: Page) {
  await page.goto("/");

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
 * Navigate to an R&D page via the sidebar.
 */
export async function navigateToRD(page: Page, route: string) {
  const testIdMap: Record<string, string> = {
    dashboard: "nav-rd-dashboard",
    programs: "nav-rd-programs",
    research: "nav-rd-research",
    workspace: "nav-rd-workspace",
    governance: "nav-rd-governance",
    deployments: "nav-rd-deployments",
    lineage: "nav-rd-lineage",
    readiness: "nav-rd-readiness",
  };
  const testId = testIdMap[route];
  if (!testId) {
    throw new Error(`Unknown R&D route: ${route}`);
  }
  await page.locator(`[data-testid="${testId}"]`).click();
}

/**
 * Navigate to an AMIS page via the sidebar.
 */
export async function navigateToAMIS(page: Page, route: "replay" | "training") {
  const testIdMap = {
    replay: "nav-amis-replay",
    training: "nav-amis-training",
  };
  await page.locator(`[data-testid="${testIdMap[route]}"]`).click();
}

/**
 * Wait for an R&D page heading to appear.
 * Readiness has a longer timeout because its API can be slow.
 */
export async function waitForRDHeading(page: Page, route: string) {
  const headingMap: Record<string, string> = {
    dashboard: "rd-dashboard-heading",
    programs: "rd-programs-heading",
    research: "rd-research-heading",
    workspace: "rd-workspace-heading",
    governance: "rd-governance-heading",
    deployments: "rd-deployments-heading",
    lineage: "rd-lineage-heading",
    readiness: "rd-readiness-heading",
  };
  const testId = headingMap[route];
  if (!testId) {
    throw new Error(`Unknown R&D route: ${route}`);
  }
  const timeout = route === "readiness" ? 25000 : 10000;
  await page.locator(`[data-testid="${testId}"]`).waitFor({ timeout });
}
