"use client";

import React from "react";
import {
  Bell,
  X,
  Minus,
  RotateCcw,
  Send,
  ShieldAlert,
  Info,
} from "lucide-react";
import {
  BrowserPermissionStatus,
  NotificationDispatchResult,
  NotificationHistoryItem,
  NotificationResultType,
  ThresholdStatus,
} from "@/types/notifications";
import { ThresholdSlider } from "./ThresholdSlider";
import { NotificationPermissionStatus } from "./NotificationPermissionStatus";
import { NotificationHistory } from "./NotificationHistory";

interface NotificationSimulatorPanelProps {
  isOpen: boolean;
  isMinimized: boolean;
  threshold: number;
  simulatedValue: number;
  thresholdStatus: ThresholdStatus;
  isArmed: boolean;
  permission: BrowserPermissionStatus;
  isSupported: boolean;
  isSecure: boolean;
  notificationCount: number;
  lastAttemptTime: string | null;
  lastAttemptResult: NotificationResultType | null;
  history: NotificationHistoryItem[];
  inAppAlertMessage: string | null;
  onClose: () => void;
  onMinimize: () => void;
  onThresholdChange: (val: number) => void;
  onIncrementThreshold: () => void;
  onDecrementThreshold: () => void;
  onSliderChange: (val: number) => void;
  onRequestPermission: () => void;
  onRefreshPermission: () => void;
  onSendTestNotification: () => NotificationDispatchResult;
  onResetSimulator: () => void;
  onClearHistory: () => void;
  onDismissInAppAlert: () => void;
}

export const NotificationSimulatorPanel: React.FC<NotificationSimulatorPanelProps> = ({
  isOpen,
  isMinimized,
  threshold,
  simulatedValue,
  thresholdStatus,
  isArmed,
  permission,
  isSupported,
  isSecure,
  notificationCount,
  lastAttemptTime,
  lastAttemptResult,
  history,
  inAppAlertMessage,
  onClose,
  onMinimize,
  onThresholdChange,
  onIncrementThreshold,
  onDecrementThreshold,
  onSliderChange,
  onRequestPermission,
  onRefreshPermission,
  onSendTestNotification,
  onResetSimulator,
  onClearHistory,
  onDismissInAppAlert,
}) => {
  if (!isOpen) return null;

  // Minimized Compact Bar
  if (isMinimized) {
    return (
      <div
        className="fixed bottom-6 right-6 z-50 bg-navy-950 text-white rounded-2xl shadow-xl border border-slate-700 p-3 flex items-center gap-3 cursor-pointer hover:bg-navy-900 transition"
        onClick={onMinimize}
        role="button"
        tabIndex={0}
        aria-label="Expand FinOps Notification Simulator"
      >
        <div className="w-8 h-8 rounded-xl bg-brand-500 text-white flex items-center justify-center font-bold">
          <Bell className="w-4 h-4" />
        </div>
        <div className="text-xs">
          <div className="font-bold flex items-center gap-1.5">
            <span>FinOps Notification Simulator</span>
            <span
              className={`w-2 h-2 rounded-full ${
                thresholdStatus === "EXCEEDED"
                  ? "bg-rose-500"
                  : thresholdStatus === "AT_THRESHOLD"
                  ? "bg-amber-400"
                  : "bg-emerald-400"
              }`}
            />
          </div>
          <div className="text-[10px] text-slate-300 font-mono">
            Value: {simulatedValue}% / Thresh: {threshold}% &bull; Click to expand
          </div>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          className="p-1 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition ml-2"
          aria-label="Close panel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  // Helper for readiness status
  const getReadinessBadge = () => {
    if (!isSupported) {
      return { label: "Unsupported", bg: "bg-slate-100 text-slate-700 border-slate-300" };
    }
    if (permission === "granted") {
      return { label: "Ready to Alert", bg: "bg-emerald-100 text-emerald-800 border-emerald-300" };
    }
    if (permission === "denied") {
      return { label: "Blocked", bg: "bg-rose-100 text-rose-800 border-rose-300" };
    }
    return { label: "Permission Needed", bg: "bg-blue-100 text-blue-800 border-blue-300" };
  };

  const readiness = getReadinessBadge();

  return (
    <div
      className="fixed bottom-6 right-6 z-50 w-[calc(100vw-2rem)] sm:w-[410px] bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[88vh] animate-in fade-in slide-in-from-bottom-4 duration-200"
      role="dialog"
      aria-labelledby="simulator-title"
      aria-describedby="simulator-subtitle"
    >
      {/* 1. Header */}
      <div className="bg-navy-950 text-white p-4 flex items-start justify-between border-b border-navy-900 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-brand-500 flex items-center justify-center text-white shadow-2xs shrink-0">
            <Bell className="w-5 h-5" />
          </div>
          <div>
            <h3 id="simulator-title" className="text-sm font-bold text-white tracking-tight">
              FinOps Notification Simulator
            </h3>
            <p id="simulator-subtitle" className="text-[11px] text-slate-300 mt-0.5">
              Simulate threshold-based alerts and desktop notifications.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onMinimize}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
            title="Minimize"
            aria-label="Minimize simulator panel"
          >
            <Minus className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
            title="Close"
            aria-label="Close simulator panel"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 2. Scrollable Body */}
      <div className="p-4 space-y-4 overflow-y-auto text-xs">
        {/* In-App Alert Banner (when threshold crossed without permission) */}
        {inAppAlertMessage && (
          <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl text-amber-900 flex items-start justify-between gap-2 shadow-2xs">
            <div className="flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <span className="font-bold text-xs">In-App Simulation Alert</span>
                <p className="text-[11px] text-amber-800 leading-normal">{inAppAlertMessage}</p>
                {permission === "default" && (
                  <button
                    type="button"
                    onClick={onRequestPermission}
                    className="mt-1 px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white font-semibold text-[10px] transition"
                  >
                    Enable Desktop Notifications Now
                  </button>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={onDismissInAppAlert}
              className="text-amber-500 hover:text-amber-800 p-0.5"
              aria-label="Dismiss in-app alert"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Browser Permission Management */}
        <NotificationPermissionStatus
          permission={permission}
          isSupported={isSupported}
          isSecure={isSecure}
          onRequestPermission={onRequestPermission}
          onRefreshPermission={onRefreshPermission}
        />

        {/* Interactive Threshold & Simulation Slider */}
        <ThresholdSlider
          threshold={threshold}
          simulatedValue={simulatedValue}
          thresholdStatus={thresholdStatus}
          isArmed={isArmed}
          onThresholdChange={onThresholdChange}
          onIncrement={onIncrementThreshold}
          onDecrement={onDecrementThreshold}
          onSliderChange={onSliderChange}
        />

        {/* Telemetry Status Grid */}
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 grid grid-cols-2 gap-2 text-[11px]">
          <div>
            <span className="text-slate-500">Readiness:</span>
            <div className="mt-0.5">
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${readiness.bg}`}>
                {readiness.label}
              </span>
            </div>
          </div>
          <div>
            <span className="text-slate-500">Alerts Sent:</span>
            <div className="font-mono font-bold text-navy-950 mt-0.5">{notificationCount}</div>
          </div>
          <div>
            <span className="text-slate-500">Last Attempt:</span>
            <div className="font-mono text-slate-700 mt-0.5 truncate">
              {lastAttemptTime || "None"}
            </div>
          </div>
          <div>
            <span className="text-slate-500">Last Result:</span>
            <div className="font-mono text-[10px] text-slate-700 mt-0.5 truncate" title={lastAttemptResult || "N/A"}>
              {lastAttemptResult ? (
                lastAttemptResult === "NATIVE_SUCCESS" ? (
                  <span className="text-emerald-700 font-semibold">Delivered</span>
                ) : (
                  <span className="text-amber-700 font-semibold">{lastAttemptResult}</span>
                )
              ) : (
                "N/A"
              )}
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 pt-1">
          <button
            type="button"
            onClick={onSendTestNotification}
            className="flex-1 py-2 px-3 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-semibold text-xs flex items-center justify-center gap-1.5 transition"
          >
            <Send className="w-3.5 h-3.5 text-brand-600" />
            <span>Send Test Alert</span>
          </button>

          <button
            type="button"
            onClick={onResetSimulator}
            className="py-2 px-3 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-semibold text-xs flex items-center justify-center gap-1.5 transition"
            title="Reset threshold to 50% and slider to 0%"
          >
            <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
            <span>Reset</span>
          </button>
        </div>

        {/* Notification History List */}
        <NotificationHistory history={history} onClearHistory={onClearHistory} />

        {/* Windows Notice */}
        <div className="p-2.5 bg-slate-100/70 border border-slate-200 rounded-lg text-[10px] text-slate-500 flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
          <span>
            Desktop alerts are rendered natively by Windows Action Center. Appearance, position, and
            sound are managed by Windows system notification preferences.
          </span>
        </div>
      </div>
    </div>
  );
};
