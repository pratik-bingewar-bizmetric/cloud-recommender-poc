"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  BrowserPermissionStatus,
  NotificationDispatchResult,
  NotificationHistoryItem,
  NotificationResultType,
  SimulatorEventType,
  ThresholdStatus,
} from "@/types/notifications";
import { BrowserNotificationService } from "./browserNotificationService";

const STORAGE_KEY_THRESHOLD = "finops_notification_simulator_threshold";
const DEFAULT_THRESHOLD = 50;

export interface UseThresholdSimulationProps {
  permission: BrowserPermissionStatus;
  onNotificationClick?: () => void;
}

export interface UseThresholdSimulationReturn {
  threshold: number;
  simulatedValue: number;
  thresholdStatus: ThresholdStatus;
  isArmed: boolean;
  notificationCount: number;
  lastAttemptTime: string | null;
  lastAttemptResult: NotificationResultType | null;
  history: NotificationHistoryItem[];
  inAppAlertMessage: string | null;
  setThreshold: (val: number) => void;
  incrementThreshold: () => void;
  decrementThreshold: () => void;
  handleSliderChange: (val: number) => void;
  sendTestAlert: () => NotificationDispatchResult;
  resetSimulator: () => void;
  clearHistory: () => void;
  dismissInAppAlert: () => void;
}

export function useThresholdSimulation({
  permission,
  onNotificationClick,
}: UseThresholdSimulationProps): UseThresholdSimulationReturn {
  // 1. Threshold configuration with localStorage persistence
  const [threshold, setThresholdState] = useState<number>(DEFAULT_THRESHOLD);

  // 2. Simulation slider state
  const [simulatedValue, setSimulatedValue] = useState<number>(0);
  const isArmedRef = useRef<boolean>(true);
  const [isArmed, setIsArmedState] = useState<boolean>(true);

  // 3. Telemetry and history
  const [notificationCount, setNotificationCount] = useState<number>(0);
  const [lastAttemptTime, setLastAttemptTime] = useState<string | null>(null);
  const [lastAttemptResult, setLastAttemptResult] =
    useState<NotificationResultType | null>(null);
  const [history, setHistory] = useState<NotificationHistoryItem[]>([]);
  const [inAppAlertMessage, setInAppAlertMessage] = useState<string | null>(null);

  // Hydrate threshold from localStorage on client mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_THRESHOLD);
      if (saved !== null) {
        const parsed = parseInt(saved, 10);
        if (!isNaN(parsed) && parsed >= 0 && parsed <= 100) {
          setThresholdState(parsed);
          // Initial arming state based on current value (0) and loaded threshold
          isArmedRef.current = 0 <= parsed;
          setIsArmedState(isArmedRef.current);
        }
      }
    } catch {
      // localStorage may be disabled in private browsing
    }
  }, []);

  // Set threshold with bounds validation and persistence
  const setThreshold = useCallback((val: number) => {
    const clamped = Math.max(0, Math.min(100, Math.round(val)));
    setThresholdState(clamped);

    try {
      localStorage.setItem(STORAGE_KEY_THRESHOLD, clamped.toString());
    } catch {}

    // Recalculate armed state without triggering an immediate notification
    // If current value is <= new threshold, arm it. If current value > new threshold, it is already exceeded (disarm).
    setSimulatedValue((currVal) => {
      if (currVal <= clamped) {
        isArmedRef.current = true;
        setIsArmedState(true);
      } else {
        isArmedRef.current = false;
        setIsArmedState(false);
      }
      return currVal;
    });
  }, []);

  const incrementThreshold = useCallback(() => {
    setThreshold(threshold + 1);
  }, [threshold, setThreshold]);

  const decrementThreshold = useCallback(() => {
    setThreshold(threshold - 1);
  }, [threshold, setThreshold]);

  // Helper to add history item
  const addHistoryItem = useCallback(
    (
      eventType: SimulatorEventType,
      thresh: number,
      simVal: number,
      perm: BrowserPermissionStatus,
      result: NotificationResultType,
      message: string
    ) => {
      const now = new Date();
      const timeFormatted = now.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });

      const newItem: NotificationHistoryItem = {
        id: `evt-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        timestamp: now.toISOString(),
        timeFormatted,
        eventType,
        threshold: thresh,
        simulatedValue: simVal,
        permissionStatus: perm,
        result,
        message,
      };

      setHistory((prev) => [newItem, ...prev.slice(0, 49)]); // keep last 50
      setLastAttemptTime(timeFormatted);
      setLastAttemptResult(result);
    },
    []
  );

  // Slider change handler with edge-triggered crossing detection
  const handleSliderChange = useCallback(
    (newVal: number) => {
      const clampedVal = Math.max(0, Math.min(100, Math.round(newVal)));
      const currThreshold = threshold;

      // Check crossing logic:
      // Condition: value crosses above threshold AND is currently armed
      if (clampedVal > currThreshold && isArmedRef.current) {
        // Disarm to prevent continuous duplicate notifications during dragging
        isArmedRef.current = false;
        setIsArmedState(false);

        // Attempt notification
        const dispatch = BrowserNotificationService.sendThresholdAlert(
          clampedVal,
          currThreshold,
          onNotificationClick
        );

        setNotificationCount((prev) => prev + 1);

        if (dispatch.nativeDelivered) {
          addHistoryItem(
            "THRESHOLD_EXCEEDED",
            currThreshold,
            clampedVal,
            permission,
            "NATIVE_SUCCESS",
            dispatch.message
          );
          setInAppAlertMessage(null);
        } else {
          // Native notification not delivered (permission default or denied or unsupported)
          let eventType: SimulatorEventType = "THRESHOLD_EXCEEDED";
          if (dispatch.resultType === "PERMISSION_DENIED") {
            eventType = "NOTIFICATION_BLOCKED";
          } else if (dispatch.resultType === "ERROR") {
            eventType = "NOTIFICATION_REQUEST_FAILED";
          }

          addHistoryItem(
            eventType,
            currThreshold,
            clampedVal,
            permission,
            dispatch.resultType,
            dispatch.message
          );

          // Prompt in-app message
          if (permission === "default") {
            setInAppAlertMessage(
              `Threshold exceeded (${clampedVal}% > ${currThreshold}%). Enable desktop notifications to receive native Windows alerts!`
            );
          } else if (permission === "denied") {
            setInAppAlertMessage(
              `Threshold exceeded (${clampedVal}% > ${currThreshold}%). Desktop notifications are blocked by your browser settings.`
            );
          } else if (permission === "unsupported") {
            setInAppAlertMessage(
              `Threshold exceeded (${clampedVal}% > ${currThreshold}%). Browser Notification API is unavailable in this environment.`
            );
          }
        }
      } else if (clampedVal <= currThreshold && !isArmedRef.current) {
        // Rearm when slider returns to or below threshold
        isArmedRef.current = true;
        setIsArmedState(true);
      }

      setSimulatedValue(clampedVal);
    },
    [threshold, permission, onNotificationClick, addHistoryItem]
  );

  // Explicit test alert
  const sendTestAlert = useCallback((): NotificationDispatchResult => {
    const res = BrowserNotificationService.sendTestAlert(onNotificationClick);
    addHistoryItem(
      "TEST_NOTIFICATION",
      threshold,
      simulatedValue,
      permission,
      res.resultType,
      res.message
    );
    if (!res.nativeDelivered && permission === "default") {
      setInAppAlertMessage(
        "Please click 'Enable Desktop Notifications' first to allow Windows desktop alerts."
      );
    }
    return res;
  }, [threshold, simulatedValue, permission, onNotificationClick, addHistoryItem]);

  // Reset simulator
  const resetSimulator = useCallback(() => {
    setThresholdState(DEFAULT_THRESHOLD);
    try {
      localStorage.setItem(STORAGE_KEY_THRESHOLD, DEFAULT_THRESHOLD.toString());
    } catch {}

    setSimulatedValue(0);
    isArmedRef.current = true;
    setIsArmedState(true);
    setNotificationCount(0);
    setLastAttemptTime(null);
    setLastAttemptResult(null);
    setInAppAlertMessage(null);
  }, []);

  // Clear history
  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  const dismissInAppAlert = useCallback(() => {
    setInAppAlertMessage(null);
  }, []);

  // Current threshold status
  let thresholdStatus: ThresholdStatus = "NORMAL";
  if (simulatedValue > threshold) {
    thresholdStatus = "EXCEEDED";
  } else if (simulatedValue === threshold) {
    thresholdStatus = "AT_THRESHOLD";
  }

  return {
    threshold,
    simulatedValue,
    thresholdStatus,
    isArmed,
    notificationCount,
    lastAttemptTime,
    lastAttemptResult,
    history,
    inAppAlertMessage,
    setThreshold,
    incrementThreshold,
    decrementThreshold,
    handleSliderChange,
    sendTestAlert,
    resetSimulator,
    clearHistory,
    dismissInAppAlert,
  };
}
