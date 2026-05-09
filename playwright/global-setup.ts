/**
 * Global Setup for Playwright Tests
 *
 * Runs once before all tests to seed test data:
 * - Creates a trading account for test_pie_e2e user
 * - Account is required for brokerId to be non-null in app
 * - Without it, BrokerSelectionModal blocks all trading UI
 */

import { request } from "@playwright/test";

async function globalSetup() {
  console.log("[globalSetup] Starting...");

  const ctx = await request.newContext();

  try {
    // Step 1: Login to get access token
    console.log("[globalSetup] Logging in test user...");
    const loginRes = await ctx.post("http://localhost:8001/auth/login", {
      data: {
        username: "test_pie_e2e",
        password: "Test123.e2e"
      }
    });

    if (!loginRes.ok()) {
      console.error(`[globalSetup] Login failed: ${loginRes.status()} ${loginRes.statusText()}`);
      throw new Error(`Login failed: ${await loginRes.text()}`);
    }

    const loginData = await loginRes.json();
    const access_token = loginData.access_token;

    if (!access_token) {
      console.error("[globalSetup] No access_token in login response");
      throw new Error("No access_token in login response");
    }

    console.log(`[globalSetup] Login successful. Token acquired: ${access_token.substring(0, 20)}...`);

    // Step 2: Create trading account (paper-broker account routed via "fyers" broker_id)
    // The system routes based on account_type:
    // - account_type="PAPER" → paper-broker-service
    // - account_type="TRADING" → actual broker plugin (fyers, etc.)
    // Idempotent: if account already exists, it returns the existing record
    console.log("[globalSetup] Creating/verifying trading account...");
    const accountRes = await ctx.post(
      "http://localhost:8005/api/v1/trading_account/fyers",
      {
        headers: {
          Authorization: `Bearer ${access_token}`,
          "Content-Type": "application/json"
        },
        data: {
          account_id: "TEST_E2E",
          account_name: "TEST_E2E",
          base_currency: "INR",
          account_type: "PAPER"  // Routes to paper-broker-service
        }
      }
    );

    if (!accountRes.ok()) {
      console.error(
        `[globalSetup] Account creation failed: ${accountRes.status()} ${accountRes.statusText()}`
      );
      console.error(`[globalSetup] Response: ${await accountRes.text()}`);
      throw new Error(`Account creation failed: ${await accountRes.text()}`);
    }

    const account = await accountRes.json();
    console.log(`[globalSetup] Trading account ready: ${account.account_id} (${account.broker_id})`);

    console.log("[globalSetup] Global setup complete ✓");
  } catch (error) {
    console.error("[globalSetup] Fatal error:", error);
    throw error;
  } finally {
    await ctx.dispose();
  }
}

export default globalSetup;
