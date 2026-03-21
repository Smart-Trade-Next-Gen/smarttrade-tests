/**
 * Playwright E2E Tests for PIE - Critical UI Paths
 *
 * Tests the most important user workflows:
 * - Navigate to PIE page
 * - Create and manage strategies
 * - Monitor real-time status
 * - Emergency kill switch activation
 */

import { test, expect, Page } from "@playwright/test";

// Test configuration
const BASE_URL = "http://localhost:5173";
const AUTH_USERNAME = "test_pie_e2e";
const AUTH_PASSWORD = "Test123.e2e";

async function loginIfNeeded(page: Page) {
  const usernameInput = page.locator('input[placeholder="Username"]');
  if (await usernameInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await usernameInput.fill(AUTH_USERNAME);
    await page.locator('input[type="password"]').fill(AUTH_PASSWORD);
    await page.locator('button:has-text("Login")').click();
  }
  // Wait for the account selection modal (accounts load async after login)
  const accountModal = page.locator('text=Select Trading Account');
  try {
    await accountModal.waitFor({ timeout: 8000 });
    await page.locator("button").filter({ hasText: "TEST_E2E" }).click();
    await accountModal.waitFor({ state: "hidden", timeout: 8000 });
  } catch {
    // Modal didn't appear — account already selected from a previous session
  }
  // Wait for sidebar PIE link to confirm app shell is loaded
  await page.locator("text=PIE").waitFor({ timeout: 10000 });
}

test.describe("PIE Critical UI Paths", () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto(BASE_URL);
    await loginIfNeeded(page);
    // Navigate to PIE via sidebar link
    await page.locator('a[href="/pie"]').click();
    await page.waitForURL("**/pie", { timeout: 10000 });
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("1. User can navigate to PIE page", async () => {
    const pieTitle = page.locator('h1:has-text("Position Intelligence Engine")');
    await expect(pieTitle).toBeVisible({ timeout: 10000 });
    console.log("✅ Successfully navigated to PIE page");
  });

  test("2. PIE page shows account-not-selected or dashboard", async () => {
    // Either the account-not-selected message or the full dashboard should appear
    const accountMsg = page.locator("text=Account Not Selected").first();
    const dashboard = page.getByRole("heading", { name: "PIE Status Dashboard" })
      .or(page.getByRole("heading", { name: "Emergency Control" })).first();
    const either = accountMsg.or(dashboard).first();
    await expect(either).toBeVisible({ timeout: 5000 });
    console.log("✅ PIE page content displayed");
  });

  test("3. WebSocket connection indicator is visible", async () => {
    const connected = page.locator("text=Connected").or(page.locator("text=Disconnected")).first();
    await expect(connected).toBeVisible({ timeout: 5000 });
    console.log("✅ WebSocket connection indicator visible");
  });

  test("4. Responsive layout on mobile viewport", async () => {
    await page.setViewportSize({ width: 375, height: 667 });
    const pieTitle = page.locator("h1");
    await expect(pieTitle).toBeVisible();
    const buttonCount = await page.locator("button").count();
    expect(buttonCount).toBeGreaterThan(0);
    await page.setViewportSize({ width: 1280, height: 720 });
    console.log("✅ Mobile responsive layout verified");
  });
});

test.describe("PIE With Account Selected", () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto(BASE_URL);
    await loginIfNeeded(page);
    await page.locator('a[href="/pie"]').click();
    await page.waitForURL("**/pie", { timeout: 10000 });
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("Kill switch button visible when account is selected", async () => {
    // Skip if no account selected
    const accountMsg = page.locator("text=Account Not Selected");
    if (await accountMsg.isVisible({ timeout: 2000 }).catch(() => false)) {
      test.skip();
      return;
    }

    const emergencySection = page.getByRole("heading", { name: "Emergency Control" });
    await emergencySection.scrollIntoViewIfNeeded();

    const killSwitchBtn = page.locator('button:has-text("Kill Switch")');
    await expect(killSwitchBtn).toBeVisible({ timeout: 5000 });
    console.log("✅ Kill switch button visible");

    // Click to open confirmation dialog
    await killSwitchBtn.click();
    const dialog = page.locator("text=Emergency Kill Switch");
    await expect(dialog).toBeVisible({ timeout: 3000 });

    // Cancel — do NOT activate
    const cancelBtn = page.locator('button:has-text("Cancel")');
    await expect(cancelBtn).toBeVisible();
    await cancelBtn.click();
    console.log("✅ Kill switch confirmation dialog works, cancelled");
  });
});
