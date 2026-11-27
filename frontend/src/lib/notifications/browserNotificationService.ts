/**
 * Browser Notification Service
 * Manages native OS desktop notifications via the standard Web Notification API.
 */

import {
  BrowserPermissionStatus,
  NotificationDispatchResult,
} from "@/types/notifications";

export interface ExtendedNotificationOptions extends NotificationOptions {
  renotify?: boolean;
}

export class BrowserNotificationService {
  /**
   * Detects whether the Notification API is supported in the current runtime environment.
   */
  public static isSupported(): boolean {
    return typeof window !== "undefined" && "Notification" in window;
  }

  /**
   * Detects whether the page is running in a secure context (HTTPS or localhost).
   */
  public static isSecure(): boolean {
    if (typeof window === "undefined") return false;
    return (
      Boolean(window.isSecureContext) ||
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1"
    );
  }

  /**
   * Reads current notification permission without triggering a prompt.
   */
  public static getPermission(): BrowserPermissionStatus {
    if (!this.isSupported()) {
      return "unsupported";
    }
    return Notification.permission as BrowserPermissionStatus;
  }

  /**
   * Requests user permission to display desktop notifications.
   * Must be called directly from an authenticated user gesture.
   */
  public static async requestPermission(): Promise<BrowserPermissionStatus> {
    if (!this.isSupported()) {
      return "unsupported";
    }

    try {
      // Modern Promise-based API with callback fallback
      let permission: NotificationPermission;
      const result = Notification.requestPermission();
      if (result && typeof result.then === "function") {
        permission = await result;
      } else {
        permission = await new Promise<NotificationPermission>((resolve) => {
          Notification.requestPermission(resolve);
        });
      }
      return permission as BrowserPermissionStatus;
    } catch {
      return "denied";
    }
  }

  /**
   * Dispatches a native desktop notification when utilization crosses the configured threshold.
   */
  public static sendThresholdAlert(
    simulatedValue: number,
    threshold: number,
    onNotificationClick?: () => void
  ): NotificationDispatchResult {
    if (!this.isSupported()) {
      return {
        success: false,
        resultType: "UNSUPPORTED",
        message: "Browser Notification API is not supported in this environment.",
        nativeDelivered: false,
      };
    }

    const permission = this.getPermission();
    if (permission === "denied") {
      return {
        success: false,
        resultType: "PERMISSION_DENIED",
        message: "Browser notifications are blocked. Enable them in site permissions.",
        nativeDelivered: false,
      };
    }

    if (permission === "default") {
      return {
        success: false,
        resultType: "PERMISSION_NOT_REQUESTED",
        message: "Notification permission has not been requested yet.",
        nativeDelivered: false,
      };
    }

    const diff = Math.max(0, simulatedValue - threshold);
    const title = "FinOps — Threshold Exceeded";
    const body = `Current utilization: ${simulatedValue}%. Configured threshold: ${threshold}%. Threshold exceeded by ${diff} percentage points.`;

    try {
      const notification = new Notification(title, {
        body,
        icon: "/favicon.ico",
        badge: "/favicon.ico",
        tag: `finops-threshold-${threshold}`,
        renotify: true,
      } as ExtendedNotificationOptions);

      notification.onclick = (e) => {
        e.preventDefault();
        try {
          if (typeof window !== "undefined") {
            window.focus();
          }
        } catch {
          // ignore focus restriction
        }
        if (onNotificationClick) {
          onNotificationClick();
        }
        try {
          notification.close();
        } catch {
          // ignore close error
        }
      };

      return {
        success: true,
        resultType: "NATIVE_SUCCESS",
        message: `Native desktop notification sent: ${title}`,
        nativeDelivered: true,
      };
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Unknown error";
      return {
        success: false,
        resultType: "ERROR",
        message: `Failed to dispatch native notification: ${errorMsg}`,
        nativeDelivered: false,
      };
    }
  }

  /**
   * Dispatches a confirmation notification upon granting permission.
   */
  public static sendConfirmation(
    onNotificationClick?: () => void
  ): NotificationDispatchResult {
    if (!this.isSupported() || this.getPermission() !== "granted") {
      return {
        success: false,
        resultType: "PERMISSION_DENIED",
        message: "Notifications are not permitted.",
        nativeDelivered: false,
      };
    }

    const title = "FinOps Notifications Enabled";
    const body =
      "You will now receive desktop alerts when your configured threshold is exceeded.";

    try {
      const notification = new Notification(title, {
        body,
        icon: "/favicon.ico",
        badge: "/favicon.ico",
        tag: "finops-confirmation",
        renotify: true,
      } as ExtendedNotificationOptions);

      notification.onclick = (e) => {
        e.preventDefault();
        try {
          if (typeof window !== "undefined") {
            window.focus();
          }
        } catch {}
        if (onNotificationClick) {
          onNotificationClick();
        }
        try {
          notification.close();
        } catch {}
      };

      return {
        success: true,
        resultType: "NATIVE_SUCCESS",
        message: "Confirmation notification dispatched.",
        nativeDelivered: true,
      };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error";
      return {
        success: false,
        resultType: "ERROR",
        message: `Notification failed: ${msg}`,
        nativeDelivered: false,
      };
    }
  }

  /**
   * Dispatches an explicit test notification to validate the workstation alert delivery.
   */
  public static sendTestAlert(
    onNotificationClick?: () => void
  ): NotificationDispatchResult {
    if (!this.isSupported()) {
      return {
        success: false,
        resultType: "UNSUPPORTED",
        message: "Notification API is not supported.",
        nativeDelivered: false,
      };
    }

    const permission = this.getPermission();
    if (permission !== "granted") {
      return {
        success: false,
        resultType: permission === "denied" ? "PERMISSION_DENIED" : "PERMISSION_NOT_REQUESTED",
        message:
          permission === "denied"
            ? "Notifications blocked by browser."
            : "Permission not yet granted.",
        nativeDelivered: false,
      };
    }

    const title = "FinOps — Test Notification";
    const body = "Desktop alerts are operational on this Windows workstation.";

    try {
      const notification = new Notification(title, {
        body,
        icon: "/favicon.ico",
        badge: "/favicon.ico",
        tag: "finops-test-alert",
        renotify: true,
      } as ExtendedNotificationOptions);

      notification.onclick = (e) => {
        e.preventDefault();
        try {
          if (typeof window !== "undefined") {
            window.focus();
          }
        } catch {}
        if (onNotificationClick) {
          onNotificationClick();
        }
        try {
          notification.close();
        } catch {}
      };

      return {
        success: true,
        resultType: "NATIVE_SUCCESS",
        message: "Test notification dispatched to operating system.",
        nativeDelivered: true,
      };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error";
      return {
        success: false,
        resultType: "ERROR",
        message: `Test notification failed: ${msg}`,
        nativeDelivered: false,
      };
    }
  }
}
