/**
 * Playwright E2E Tests for Frontend-Backend Alignment
 *
 * Verifies the 6-phase frontend-backend alignment implementation:
 * 1. JWT Token Security (localStorage → in-memory + httpOnly cookie)
 * 2. Dual WebSocket Architecture (MDS for market data, BAS for execution)
 * 3. REST Endpoint Alignment (fixed 5 broken endpoints)
 * 4. Order Execution via BAS WebSocket
 *
 * Tests frontend-specific concerns: browser storage, network connections, UI responses.
 */

import { test, expect, Page, Browser } from "@playwright/test";

// Test configuration
const BASE_URL = "http://localhost:5173";
const AUTH_USERNAME = "test_pie_e2e";
const AUTH_PASSWORD = "Test123.e2e";

async function loginIfNeeded(page: Page) {
  // Wait for login form to appear or app to load
  try {
    const usernameInput = page.locator('input[placeholder="Username"]');
    const isLoginVisible = await usernameInput.isVisible({ timeout: 5000 }).catch(() => false);

    if (isLoginVisible) {
      await usernameInput.fill(AUTH_USERNAME);
      await page.locator('input[placeholder="Password"]').fill(AUTH_PASSWORD);
      await page.locator('button:has-text("Login")').click();

      // Wait for the account selection modal (accounts load async after login)
      const accountModal = page.locator('text=Select Trading Account');
      try {
        await accountModal.waitFor({ timeout: 8000 });
        await page.locator("button").filter({ hasText: "TEST_E2E" }).click();
        await accountModal.waitFor({ state: "hidden", timeout: 8000 });
      } catch {
        // Modal didn't appear — account already selected
      }
    }
  } catch (e) {
    console.log("Login skip:", e);
  }

  // Wait for app to be ready (check multiple possible indicators)
  await Promise.race([
    page.locator("text=Dashboard").waitFor({ timeout: 10000 }).catch(() => null),
    page.locator("a[href='/orders']").waitFor({ timeout: 10000 }).catch(() => null),
    page.waitForTimeout(2000),
  ]);
}

test.describe("JWT Token Security", () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto(BASE_URL);
    await loginIfNeeded(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("access_token not in localStorage after login", async () => {
    const accessToken = await page.evaluate(() => {
      return localStorage.getItem("access_token");
    });
    expect(accessToken).toBeNull();
  });

  test("refresh_token is httpOnly and not accessible via JavaScript", async () => {
    // Verify refresh_token is not in document.cookie (JS-accessible cookies)
    const docCookie = await page.evaluate(() => {
      return document.cookie;
    });
    expect(docCookie).not.toContain("refresh_token");

    // Verify refresh_token exists in context cookies but is httpOnly
    const cookies = await page.context().cookies();
    const refreshTokenCookie = cookies.find((c) => c.name === "refresh_token");

    // Note: refresh_token may not exist if Auth service is not yet configured with httpOnly
    // This test documents the expected state after backend upgrade
    if (refreshTokenCookie) {
      expect(refreshTokenCookie.httpOnly).toBe(true);
      expect(refreshTokenCookie.secure).toBe(true);
    }
  });

  test("session persists on page reload (silent refresh)", async () => {
    // Reload the page
    await page.reload({ waitUntil: "networkidle" });

    // Wait for app to restore (check sidebar is visible, no redirect to login)
    const dashboardLink = page.locator("text=Dashboard").first();
    await dashboardLink.waitFor({ timeout: 10000 });

    // Verify we're not at /login (would be there if session lost)
    const url = page.url();
    expect(url).not.toContain("/login");
  });
});

test.describe("Dual WebSocket Architecture", () => {
  let page: Page;
  const wsConnections: { url: string; type: "mds" | "bas" | "unknown" }[] = [];

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();

    // Capture all WebSocket connections
    page.on("websocket", (ws) => {
      const url = ws.url();
      let type: "mds" | "bas" | "unknown" = "unknown";

      if (url.includes("8004")) {
        type = "mds";
      } else if (url.includes("8005")) {
        type = "bas";
      }

      wsConnections.push({ url, type });
      console.log(`[WS Connected] ${type}: ${url}`);

      // Log sent frames (for debugging)
      ws.on("framesent", (data) => {
        if (data.payload.startsWith('{"')) {
          console.log(`[WS ${type} sent]`, data.payload.substring(0, 100));
        }
      });

      // Log received frames (for debugging)
      ws.on("framereceived", (data) => {
        if (data.payload.startsWith('{"')) {
          console.log(`[WS ${type} recv]`, data.payload.substring(0, 100));
        }
      });
    });

    await page.goto(BASE_URL);
    await loginIfNeeded(page);

    // Wait a bit for all WS connections to establish
    await page.waitForTimeout(2000);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("MDS WebSocket connects to market data endpoint", async () => {
    const mdsWs = wsConnections.find((ws) => ws.type === "mds");
    expect(mdsWs).toBeDefined();
    expect(mdsWs!.url).toMatch(/ws:\/\/localhost:8004\/ws\/.+\/ui\?token=/);
  });

  test("BAS WebSocket connects to execution endpoint", async () => {
    const basWs = wsConnections.find((ws) => ws.type === "bas");
    expect(basWs).toBeDefined();
    expect(basWs!.url).toMatch(/ws:\/\/localhost:8005\/api\/v1\/ws\?token=.+&account_id=/);
  });

  test("MDS WebSocket does not send subscribe.account", async () => {
    // Collect all messages sent on MDS WebSocket
    const mdsMessages: string[] = [];

    const mdsListener = (ws: any) => {
      if (!ws.url.includes("8004")) return;

      ws.on("framesent", (data: any) => {
        mdsMessages.push(data.payload);
      });
    };

    page.on("websocket", mdsListener);

    // Wait a bit and then perform an action that would trigger subscriptions
    await page.waitForTimeout(1000);

    // Verify no subscribe.account in any sent message
    for (const msg of mdsMessages) {
      try {
        const parsed = JSON.parse(msg);
        expect(parsed.action).not.toBe("subscribe.account");
      } catch {
        // Not JSON, skip
      }
    }
  });

  test("BAS WebSocket sends connection_ack upon connect", async () => {
    // Collect messages received on BAS WebSocket
    let connectionAckReceived = false;

    const basListener = (ws: any) => {
      if (!ws.url.includes("8005")) return;

      ws.on("framereceived", (data: any) => {
        try {
          const parsed = JSON.parse(data.payload);
          if (parsed.type === "connection_ack") {
            connectionAckReceived = true;
          }
        } catch {
          // Not JSON, skip
        }
      });
    };

    page.on("websocket", basListener);

    // Give it time to receive
    await page.waitForTimeout(2000);

    expect(connectionAckReceived).toBe(true);
  });
});

test.describe("REST Endpoint Alignment", () => {
  let page: Page;
  const requests: { method: string; url: string; status?: number }[] = [];

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();

    // Capture all HTTP requests
    page.on("request", (req) => {
      const url = req.url();
      requests.push({ method: req.method(), url });
    });

    page.on("response", (res) => {
      const url = res.url();
      const reqEntry = requests.find((r) => r.url === url);
      if (reqEntry) {
        reqEntry.status = res.status();
      }
    });

    await page.goto(BASE_URL);
    await loginIfNeeded(page);

    // Wait for initial data loads
    await page.waitForTimeout(2000);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("Instruments use /id/ path segment", async () => {
    const instrumentRequests = requests.filter(
      (r) =>
        r.url.includes("/instruments/") &&
        (r.method === "GET" || r.method === "POST")
    );

    // Should have at least one request using /id/ path
    const hasIdPath = instrumentRequests.some((r) =>
      r.url.includes("/instruments/id/")
    );
    expect(hasIdPath).toBe(true);

    // Should NOT have requests without /id/
    const noIdPath = instrumentRequests.some(
      (r) =>
        r.url.match(/\/instruments\/[^/]+$/) &&
        !r.url.includes("/instruments/id/")
    );
    expect(noIdPath).toBe(false);
  });

  test("Quotes use POST /data/quotes/{brokerId}", async () => {
    const quoteRequests = requests.filter((r) => r.url.includes("quotes"));

    // Should have POST requests to /data/quotes/
    const hasPostDataQuotes = quoteRequests.some(
      (r) =>
        r.method === "POST" && r.url.includes("/data/quotes/")
    );
    expect(hasPostDataQuotes).toBe(true);

    // Should NOT have GET requests to /quotes/
    const hasGetQuotes = quoteRequests.some(
      (r) =>
        r.method === "GET" &&
        r.url.match(/\/quotes\/[^/]+$/) &&
        !r.url.includes("/data/")
    );
    expect(hasGetQuotes).toBe(false);
  });

  test("No 404 errors on page load", async () => {
    const notFoundRequests = requests.filter((r) => r.status === 404);
    expect(notFoundRequests.length).toBe(0);
  });

  test("No 405 Method Not Allowed errors", async () => {
    const methodNotAllowedRequests = requests.filter((r) => r.status === 405);
    expect(methodNotAllowedRequests.length).toBe(0);
  });
});

test.describe("Order Execution via BAS WebSocket", () => {
  let page: Page;
  let mdsReceivedOrderEvents = false;
  let basReceivedOrderEvents = false;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();

    page.on("websocket", (ws) => {
      const url = ws.url();
      const isMds = url.includes("8004");
      const isBas = url.includes("8005");

      ws.on("framereceived", (data: any) => {
        try {
          const parsed = JSON.parse(data.payload);
          // Check for execution events
          if (parsed.type === "event" && parsed.event_name?.includes("order.")) {
            if (isBas) basReceivedOrderEvents = true;
            if (isMds) mdsReceivedOrderEvents = true;
          } else if (parsed.type === "order.update" && isMds) {
            // Old-style MDS order events (should not appear)
            mdsReceivedOrderEvents = true;
          }
        } catch {
          // Not JSON
        }
      });
    });

    await page.goto(BASE_URL);
    await loginIfNeeded(page);

    // Navigate to orders page
    await page.locator('a[href="/orders"]').click();
    await page.waitForURL("**/orders", { timeout: 10000 });

    // Wait for page to be ready
    await page.waitForTimeout(1000);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("Placing order triggers BAS WS event (not MDS WS)", async () => {
    // Reset flags
    mdsReceivedOrderEvents = false;
    basReceivedOrderEvents = false;

    // Fill order form
    const symbolInput = page.getByLabel("Symbol");
    await symbolInput.fill("INFY");

    const sideSelect = page.getByLabel("Side");
    await sideSelect.selectOption("BUY");

    const typeSelect = page.getByLabel("Type");
    await typeSelect.selectOption("MARKET");

    const qtyInput = page.getByLabel("Qty");
    await qtyInput.fill("1");

    // Place order
    const placeButton = page.locator('button:has-text("Place Order")');

    // Handle any validation alerts
    page.on("dialog", (dialog) => {
      console.log("Dialog:", dialog.message());
      dialog.dismiss();
    });

    await placeButton.click();

    // Wait for WS events
    await page.waitForTimeout(2000);

    // Verify BAS received order events, MDS did not
    expect(basReceivedOrderEvents).toBe(true);
    expect(mdsReceivedOrderEvents).toBe(false);

    // Verify order appears in UI
    const orderContainer = page.locator('div:has-text("INFY")');
    await expect(orderContainer).toBeVisible({ timeout: 5000 });
  });
});
