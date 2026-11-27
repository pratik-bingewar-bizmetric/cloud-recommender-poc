/**
 * Shared Type Definitions for the FinOps Notification Simulator
 */

export type BrowserPermissionStatus = "granted" | "denied" | "default" | "unsupported";

export type NotificationResultType =
  | "NATIVE_SUCCESS"
  | "PERMISSION_DENIED"
  | "PERMISSION_NOT_REQUESTED"
  | "UNSUPPORTED"
  | "IN_APP_FALLBACK"
  | "ERROR";

export type SimulatorEventType =
  | "THRESHOLD_EXCEEDED"
  | "TEST_NOTIFICATION"
  | "PERMISSION_GRANTED"
  | "PERMISSION_DENIED"
  | "NOTIFICATION_BLOCKED"
  | "NOTIFICATION_REQUEST_FAILED"
  | "CONFIRMATION_NOTIFICATION";

export type ThresholdStatus = "NORMAL" | "AT_THRESHOLD" | "EXCEEDED";

export interface NotificationHistoryItem {
  id: string;
  timestamp: string;
  timeFormatted: string;
  eventType: SimulatorEventType;
  threshold: number;
  simulatedValue: number;
  permissionStatus: BrowserPermissionStatus;
  result: NotificationResultType;
  message: string;
}

export interface NotificationDispatchResult {
  success: boolean;
  resultType: NotificationResultType;
  message: string;
  nativeDelivered: boolean;
}

export interface SimulatorState {
  threshold: number;
  simulatedValue: number;
  isArmed: boolean;
  notificationCount: number;
  lastAttemptTime: string | null;
  lastAttemptResult: NotificationResultType | null;
  history: NotificationHistoryItem[];
  inAppAlertMessage: string | null;
}

