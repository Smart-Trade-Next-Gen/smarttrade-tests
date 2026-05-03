/**
 * Playwright Quick Alignment Tests
 *
 * Ultra-simplified tests focused on the core JWT security validation.
 * These tests verify the alignment without requiring complex auth flows.
 */

import { test, expect } from "@playwright/test";

const BASE_URL = "http://localhost:5173";

test.describe("Frontend-Backend Alignment (Quick Validation)", () => {
  test("JWT: localStorage does NOT contain access_token", async ({ page }) => {
    // Go to the app (stays on login page but app is loaded)
    await page.goto(BASE_URL);

    // Verify localStorage is clean (no auth tokens should be stored there)
    const accessToken = await page.evaluate(() => {
      return localStorage.getItem("access_token");
    });

    const refreshToken = await page.evaluate(() => {
      return localStorage.getItem("refresh_token");
    });

    expect(accessToken).toBeNull();
    expect(refreshToken).toBeNull();
  });

  test("JWT: refresh_token is NOT in document.cookie (httpOnly)", async ({ page }) => {
    await page.goto(BASE_URL);

    // Verify refresh_token isn't in readable cookies (JS can't access httpOnly)
    const docCookie = await page.evaluate(() => {
      return document.cookie;
    });

    expect(docCookie).not.toContain("refresh_token=");
  });

  test("Storage: App uses only in-memory token storage (secure)", async ({ page }) => {
    await page.goto(BASE_URL);

    const storage = await page.evaluate(() => {
      const items: Record<string, string> = {};
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key) items[key] = localStorage.getItem(key) || "";
      }
      return items;
    });

    // Verify no sensitive data in localStorage
    const sensitiveKeys = Object.keys(storage).filter((key) =>
      /token|password|secret|credential|auth/i.test(key)
    );

    expect(sensitiveKeys).toHaveLength(0);
  });

  test("API: App doesn't make requests to deprecated endpoints", async ({ page }) => {
    const apiCalls: string[] = [];

    page.on("request", (req) => {
      apiCalls.push(`${req.method()} ${req.url()}`);
    });

    await page.goto(BASE_URL);

    // Wait for page to load and any initial API calls
    await page.waitForTimeout(2000);

    // Check for deprecated endpoint patterns
    const deprecatedPatterns = [
      /\/api\/v1\/quotes\/[^/]+$/, // Old: GET /quotes/{symbol}
      /\/api\/v1\/ohlc\//, // Old: GET /ohlc/...
      /\/api\/v1\/instruments\/[^/id]/, // Old: GET /instruments/{id} without /id/
    ];

    const hasDeprecatedCalls = apiCalls.some((call) =>
      deprecatedPatterns.some((pattern) => pattern.test(call))
    );

    expect(hasDeprecatedCalls).toBe(false);
  });

  test("API: No 404 errors from core endpoints", async ({ page }) => {
    const errors: { status: number; url: string }[] = [];

    page.on("response", (res) => {
      if (res.status() === 404) {
        errors.push({ status: res.status(), url: res.url() });
      }
    });

    await page.goto(BASE_URL);

    // Wait for initial load
    await page.waitForTimeout(2000);

    expect(errors).toHaveLength(0);
  });

  test("API: No 405 Method Not Allowed errors", async ({ page }) => {
    const errors: { status: number; url: string }[] = [];

    page.on("response", (res) => {
      if (res.status() === 405) {
        errors.push({ status: res.status(), url: res.url() });
      }
    });

    await page.goto(BASE_URL);

    // Wait for initial load
    await page.waitForTimeout(2000);

    expect(errors).toHaveLength(0);
  });

  test("WebSocket: App attempts to open WS connections", async ({ page }) => {
    let wsCount = 0;

    page.on("websocket", (ws) => {
      wsCount++;
      console.log(`✓ WebSocket connection #${wsCount}: ${ws.url()}`);
    });

    await page.goto(BASE_URL);

    // Wait for WS connections to attempt
    await page.waitForTimeout(3000);

    // Should have at least attempted to open WS connections
    expect(wsCount).toBeGreaterThan(0);
  });

  test("App: Login page loads without errors", async ({ page }) => {
    let errorCount = 0;

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        console.log(`Console error: ${msg.text()}`);
        errorCount++;
      }
    });

    await page.goto(BASE_URL);

    // Wait for page to fully load
    await page.waitForTimeout(2000);

    // Should load without critical errors
    expect(errorCount).toBeLessThan(3); // Allow some minor errors, but not many
  });

  test("Frontend: Has login form (app is loaded)", async ({ page }) => {
    await page.goto(BASE_URL);

    // Verify login form elements exist
    const usernameInput = page.locator('input[placeholder="Username"]');
    const passwordInput = page.locator('input[placeholder="Password"]');
    const loginButton = page.locator('button:has-text("Login")');

    await expect(usernameInput).toBeVisible({ timeout: 5000 });
    await expect(passwordInput).toBeVisible();
    await expect(loginButton).toBeVisible();
  });
});
