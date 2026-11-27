/**
 * Automated Test Suite: FinOps Notification Simulator with Native Windows Notifications
 * Verifies threshold-based simulation, edge-triggered crossing, and native Notification API integration.
 */

import assert from "node:assert";
import test from "node:test";
import { BrowserNotificationService } from "../src/lib/notifications/browserNotificationService";

// Helper to set up mock browser environment
interface MockNotificationCall {
  title: string;
  options?: NotificationOptions & { renotify?: boolean };
}

class MockNotification {
  public static calls: MockNotificationCall[] = [];
  public static permission: NotificationPermission = "default";
  public static shouldThrow = false;
  public onclick: ((e: any) => void) | null = null;

  public title: string;
  public options?: NotificationOptions;

  constructor(title: string, options?: NotificationOptions) {
    if (MockNotification.shouldThrow) {
      throw new Error("Simulated browser security exception");
    }
    this.title = title;
    this.options = options;
    MockNotification.calls.push({ title, options });
  }

  public static requestPermission(cb?: (p: NotificationPermission) => void): Promise<NotificationPermission> {
    if (cb) cb(MockNotification.permission);
    return Promise.resolve(MockNotification.permission);
  }

  public close(): void {}
}

function setupMockBrowser(options: {
  supported?: boolean;
  secure?: boolean;
  permission?: NotificationPermission;
  shouldThrow?: boolean;
}) {
  MockNotification.calls = [];
  MockNotification.permission = options.permission ?? "granted";
  MockNotification.shouldThrow = options.shouldThrow ?? false;

  (globalThis as any).window = {
    isSecureContext: options.secure ?? true,
    location: { hostname: "localhost" },
    focus: () => {},
  };

  if (options.supported !== false) {
    (globalThis as any).window.Notification = MockNotification;
    (globalThis as any).Notification = MockNotification;
  } else {
    delete (globalThis as any).window.Notification;
    delete (globalThis as any).Notification;
  }
}

// -------------------------------------------------------------
// 1. Browser Notification Service & Permission Tests
// -------------------------------------------------------------

test("Notification Service: Detects supported and secure context on localhost", () => {
  setupMockBrowser({ supported: true, secure: true, permission: "granted" });
  assert.strictEqual(BrowserNotificationService.isSupported(), true);
  assert.strictEqual(BrowserNotificationService.isSecure(), true);
  assert.strictEqual(BrowserNotificationService.getPermission(), "granted");
});

test("Notification Service: Detects unsupported environment gracefully", () => {
  setupMockBrowser({ supported: false });
  assert.strictEqual(BrowserNotificationService.isSupported(), false);
  assert.strictEqual(BrowserNotificationService.getPermission(), "unsupported");

  const alertResult = BrowserNotificationService.sendThresholdAlert(70, 50);
  assert.strictEqual(alertResult.success, false);
  assert.strictEqual(alertResult.resultType, "UNSUPPORTED");
  assert.strictEqual(alertResult.nativeDelivered, false);
});

test("Notification Service: Handles permission default / not yet requested", () => {
  setupMockBrowser({ supported: true, permission: "default" });
  assert.strictEqual(BrowserNotificationService.getPermission(), "default");

  const alertResult = BrowserNotificationService.sendThresholdAlert(60, 50);
  assert.strictEqual(alertResult.success, false);
  assert.strictEqual(alertResult.resultType, "PERMISSION_NOT_REQUESTED");
  assert.strictEqual(alertResult.nativeDelivered, false);
});

test("Notification Service: Handles permission denied / blocked without throwing", () => {
  setupMockBrowser({ supported: true, permission: "denied" });
  assert.strictEqual(BrowserNotificationService.getPermission(), "denied");

  const alertResult = BrowserNotificationService.sendThresholdAlert(80, 50);
  assert.strictEqual(alertResult.success, false);
  assert.strictEqual(alertResult.resultType, "PERMISSION_DENIED");
  assert.strictEqual(alertResult.nativeDelivered, false);
  assert.strictEqual(MockNotification.calls.length, 0);
});

test("Notification Service: Requests permission and resolves granted", async () => {
  setupMockBrowser({ supported: true, permission: "granted" });
  const perm = await BrowserNotificationService.requestPermission();
  assert.strictEqual(perm, "granted");
});

test("Notification Service: Dispatches threshold alert with accurate title, body, and tags", () => {
  setupMockBrowser({ supported: true, permission: "granted" });

  let clicked = false;
  const result = BrowserNotificationService.sendThresholdAlert(72, 50, () => {
    clicked = true;
  });

  assert.strictEqual(result.success, true);
  assert.strictEqual(result.resultType, "NATIVE_SUCCESS");
  assert.strictEqual(result.nativeDelivered, true);
  assert.strictEqual(MockNotification.calls.length, 1);

  const call = MockNotification.calls[0];
  assert.strictEqual(call.title, "FinOps — Threshold Exceeded");
  assert.ok(call.options?.body?.includes("Current utilization: 72%"));
  assert.ok(call.options?.body?.includes("Configured threshold: 50%"));
  assert.ok(call.options?.body?.includes("exceeded by 22 percentage points"));
  assert.strictEqual(call.options?.tag, "finops-threshold-50");
  assert.strictEqual((call.options as any)?.renotify, true);
});

test("Notification Service: Dispatches confirmation notification upon permission grant", () => {
  setupMockBrowser({ supported: true, permission: "granted" });

  const result = BrowserNotificationService.sendConfirmation();
  assert.strictEqual(result.success, true);
  assert.strictEqual(result.resultType, "NATIVE_SUCCESS");
  assert.strictEqual(MockNotification.calls.length, 1);
  assert.strictEqual(MockNotification.calls[0].title, "FinOps Notifications Enabled");
  assert.ok(MockNotification.calls[0].options?.body?.includes("You will now receive desktop alerts"));
});

test("Notification Service: Dispatches explicit test alert independently of slider", () => {
  setupMockBrowser({ supported: true, permission: "granted" });

  const result = BrowserNotificationService.sendTestAlert();
  assert.strictEqual(result.success, true);
  assert.strictEqual(result.resultType, "NATIVE_SUCCESS");
  assert.strictEqual(MockNotification.calls.length, 1);
  assert.strictEqual(MockNotification.calls[0].title, "FinOps — Test Notification");
});

test("Notification Service: Catches and reports Notification API runtime errors", () => {
  setupMockBrowser({ supported: true, permission: "granted", shouldThrow: true });

  const result = BrowserNotificationService.sendThresholdAlert(90, 50);
  assert.strictEqual(result.success, false);
  assert.strictEqual(result.resultType, "ERROR");
  assert.strictEqual(result.nativeDelivered, false);
  assert.ok(result.message.includes("Simulated browser security exception"));
});

// -------------------------------------------------------------
// 2. Threshold Crossing & Edge-Triggered State Machine Tests
// -------------------------------------------------------------

class ThresholdSimulationEngine {
  public threshold = 50;
  public simulatedValue = 0;
  public isArmed = true;
  public notificationCount = 0;
  public history: Array<{ value: number; threshold: number; event: string }> = [];

  constructor(defaultThreshold = 50) {
    this.threshold = this.clampThreshold(defaultThreshold);
    this.isArmed = 0 <= this.threshold;
  }

  public clampThreshold(val: number): number {
    return Math.max(0, Math.min(100, Math.round(val)));
  }

  public setThreshold(val: number): void {
    const clamped = this.clampThreshold(val);
    this.threshold = clamped;
    // Changing threshold must never self-trigger notifications
    if (this.simulatedValue <= clamped) {
      this.isArmed = true;
    } else {
      this.isArmed = false;
    }
  }

  public onSliderChange(newVal: number): boolean {
    const clampedVal = Math.max(0, Math.min(100, Math.round(newVal)));
    let triggered = false;

    if (clampedVal > this.threshold && this.isArmed) {
      this.isArmed = false;
      this.notificationCount++;
      triggered = true;
      this.history.push({
        value: clampedVal,
        threshold: this.threshold,
        event: "THRESHOLD_EXCEEDED",
      });
    } else if (clampedVal <= this.threshold && !this.isArmed) {
      this.isArmed = true;
    }

    this.simulatedValue = clampedVal;
    return triggered;
  }

  public reset(): void {
    this.threshold = 50;
    this.simulatedValue = 0;
    this.isArmed = true;
    this.notificationCount = 0;
    this.history = [];
  }
}

test("Threshold Logic: Default threshold is 50% and clamps within 0–100%", () => {
  const engine = new ThresholdSimulationEngine();
  assert.strictEqual(engine.threshold, 50);
  assert.strictEqual(engine.simulatedValue, 0);
  assert.strictEqual(engine.isArmed, true);

  engine.setThreshold(-10);
  assert.strictEqual(engine.threshold, 0);

  engine.setThreshold(150);
  assert.strictEqual(engine.threshold, 100);

  engine.setThreshold(72.6);
  assert.strictEqual(engine.threshold, 73);
});

test("Threshold Logic: Exact threshold equality does NOT trigger notification", () => {
  const engine = new ThresholdSimulationEngine(50);
  const triggeredAt50 = engine.onSliderChange(50);
  assert.strictEqual(triggeredAt50, false);
  assert.strictEqual(engine.notificationCount, 0);
  assert.strictEqual(engine.isArmed, true);
});

test("Threshold Logic: Upward crossing triggers exactly one alert", () => {
  const engine = new ThresholdSimulationEngine(50);
  const triggeredAt51 = engine.onSliderChange(51);
  assert.strictEqual(triggeredAt51, true);
  assert.strictEqual(engine.notificationCount, 1);
  assert.strictEqual(engine.isArmed, false);
});

test("Threshold Logic: Continuous dragging above threshold generates zero duplicates", () => {
  const engine = new ThresholdSimulationEngine(50);

  assert.strictEqual(engine.onSliderChange(51), true); // First trigger
  assert.strictEqual(engine.onSliderChange(75), false); // Duplicate suppressed
  assert.strictEqual(engine.onSliderChange(90), false); // Duplicate suppressed
  assert.strictEqual(engine.onSliderChange(100), false); // Duplicate suppressed
  assert.strictEqual(engine.notificationCount, 1);
});

test("Threshold Logic: Returning to or below threshold rearms the trigger", () => {
  const engine = new ThresholdSimulationEngine(50);

  engine.onSliderChange(55); // Triggered
  assert.strictEqual(engine.notificationCount, 1);
  assert.strictEqual(engine.isArmed, false);

  engine.onSliderChange(40); // Downward crossing: rearm
  assert.strictEqual(engine.isArmed, true);

  const retriggered = engine.onSliderChange(60); // Second upward crossing
  assert.strictEqual(retriggered, true);
  assert.strictEqual(engine.notificationCount, 2);
});

test("Threshold Logic: Strict verification of Section 8 specification scenario table", () => {
  const engine = new ThresholdSimulationEngine(50);

  // Scenario 1: 0 -> 30 (threshold 50) -> No notification
  assert.strictEqual(engine.onSliderChange(30), false);
  assert.strictEqual(engine.notificationCount, 0);

  // Scenario 2: 30 -> 50 (50) -> No notification
  assert.strictEqual(engine.onSliderChange(50), false);
  assert.strictEqual(engine.notificationCount, 0);

  // Scenario 3: 50 -> 51 (50) -> Send notification
  assert.strictEqual(engine.onSliderChange(51), true);
  assert.strictEqual(engine.notificationCount, 1);

  // Scenario 4: 51 -> 75 (50) -> No duplicate
  assert.strictEqual(engine.onSliderChange(75), false);
  assert.strictEqual(engine.notificationCount, 1);

  // Scenario 5: 75 -> 90 (50) -> No duplicate
  assert.strictEqual(engine.onSliderChange(90), false);
  assert.strictEqual(engine.notificationCount, 1);

  // Scenario 6: 90 -> 40 (50) -> Rearm notification
  assert.strictEqual(engine.onSliderChange(40), false);
  assert.strictEqual(engine.isArmed, true);
  assert.strictEqual(engine.notificationCount, 1);

  // Scenario 7: 40 -> 60 (50) -> Send new notification
  assert.strictEqual(engine.onSliderChange(60), true);
  assert.strictEqual(engine.notificationCount, 2);
});

test("Threshold Logic: Boundary values at 0% and 100%", () => {
  // Boundary 1: At 100%, max slider value is 100%, so value can never exceed threshold
  const engine100 = new ThresholdSimulationEngine(100);
  assert.strictEqual(engine100.onSliderChange(100), false);
  assert.strictEqual(engine100.notificationCount, 0);

  // Boundary 2: At 0%, moving from 0 to 1 immediately triggers
  const engine0 = new ThresholdSimulationEngine(0);
  assert.strictEqual(engine0.isArmed, true);
  assert.strictEqual(engine0.onSliderChange(1), true);
  assert.strictEqual(engine0.notificationCount, 1);
});

test("Threshold Logic: Changing threshold configuration does not self-trigger", () => {
  const engine = new ThresholdSimulationEngine(50);
  engine.onSliderChange(45); // Below threshold 50

  // Lower threshold to 30: current value 45 is now above 30, but must NOT trigger notification on config change!
  engine.setThreshold(30);
  assert.strictEqual(engine.notificationCount, 0);
  assert.strictEqual(engine.isArmed, false); // disarmed because already above

  // Dragging higher (45 -> 50) does not duplicate
  assert.strictEqual(engine.onSliderChange(50), false);

  // Returning below new threshold 30 rearms
  engine.onSliderChange(20);
  assert.strictEqual(engine.isArmed, true);

  // Now crossing above 30 triggers
  assert.strictEqual(engine.onSliderChange(35), true);
  assert.strictEqual(engine.notificationCount, 1);
});

test("Threshold Logic: Reset Simulator restores initial 50% threshold and 0% slider", () => {
  const engine = new ThresholdSimulationEngine(75);
  engine.onSliderChange(80);
  assert.strictEqual(engine.notificationCount, 1);
  assert.strictEqual(engine.history.length, 1);

  engine.reset();
  assert.strictEqual(engine.threshold, 50);
  assert.strictEqual(engine.simulatedValue, 0);
  assert.strictEqual(engine.isArmed, true);
  assert.strictEqual(engine.notificationCount, 0);
  assert.strictEqual(engine.history.length, 0);
});

