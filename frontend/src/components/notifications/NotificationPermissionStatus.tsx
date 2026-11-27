"use client";

import React, { useState } from "react";
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { BrowserPermissionStatus } from "@/types/notifications";

interface NotificationPermissionStatusProps {
  permission: BrowserPermissionStatus;
  isSupported: boolean;
  isSecure: boolean;
  onRequestPermission: () => void;
  onRefreshPermission: () => void;
}

export const NotificationPermissionStatus: React.FC<NotificationPermissionStatusProps> = ({
  permission,
  isSupported,
  isSecure,
  onRequestPermission,
  onRefreshPermission,
}) => {
  const [showInstructions, setShowInstructions] = useState<boolean>(false);

  // 1. UNSUPPORTED OR INSECURE CONTEXT
  if (!isSupported || !isSecure) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-900 space-y-1.5">
        <div className="flex items-center gap-1.5 font-bold text-amber-800">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span>Desktop Notifications Unavailable</span>
        </div>
        <p className="text-[11px] text-amber-800/90 leading-relaxed">
          {!isSupported
            ? "Your current browser does not support the Web Notification API. In-app simulation alerts will be displayed instead."
            : "Native notifications require a secure origin (HTTPS or localhost). Insecure HTTP origins are blocked by browser security."}
        </p>
      </div>
    );
  }

  // 2. PERMISSION GRANTED
  if (permission === "granted") {
    return (
      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-xs flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-700 shrink-0">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div>
            <div className="font-bold text-emerald-950 text-xs">Desktop notifications enabled</div>
            <p className="text-[11px] text-emerald-700">
              Windows notifications will trigger when threshold is exceeded.
            </p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
          Ready
        </span>
      </div>
    );
  }

  // 3. PERMISSION DENIED / BLOCKED
  if (permission === "denied") {
    return (
      <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 text-xs space-y-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2">
            <div className="w-7 h-7 rounded-lg bg-rose-100 flex items-center justify-center text-rose-700 shrink-0 mt-0.5">
              <XCircle className="w-4 h-4" />
            </div>
            <div>
              <div className="font-bold text-rose-950 text-xs">Browser notifications are blocked</div>
              <p className="text-[11px] text-rose-700 mt-0.5">
                Notifications are blocked in your browser site permissions.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onRefreshPermission}
            title="Recheck Permission"
            className="p-1 rounded-md border border-rose-200 bg-white hover:bg-rose-100 text-rose-800 transition shrink-0"
            aria-label="Recheck notification permission"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="pt-1">
          <button
            type="button"
            onClick={() => setShowInstructions((prev) => !prev)}
            className="text-[11px] font-semibold text-rose-800 hover:text-rose-900 flex items-center gap-1 transition"
          >
            <HelpCircle className="w-3.5 h-3.5" />
            <span>How to Enable Notifications</span>
            {showInstructions ? (
              <ChevronUp className="w-3 h-3 ml-0.5" />
            ) : (
              <ChevronDown className="w-3 h-3 ml-0.5" />
            )}
          </button>

          {showInstructions && (
            <div className="mt-2 p-2.5 bg-white border border-rose-200 rounded-lg text-[11px] text-slate-700 space-y-2">
              <div>
                <strong className="text-navy-950">Google Chrome:</strong>
                <ol className="list-decimal pl-4 mt-0.5 space-y-0.5 text-slate-600">
                  <li>Click the View Site Information icon (tune/sliders) to the left of the address bar.</li>
                  <li>Locate <strong>Notifications</strong> and toggle it from <em>Block</em> to <em>Allow</em>.</li>
                  <li>Click <em>Recheck Permission</em> above or refresh the page.</li>
                </ol>
              </div>
              <div className="pt-1 border-t border-slate-100">
                <strong className="text-navy-950">Microsoft Edge:</strong>
                <ol className="list-decimal pl-4 mt-0.5 space-y-0.5 text-slate-600">
                  <li>Click the Lock or Site Information icon beside the address bar.</li>
                  <li>Click <strong>Permissions for this site</strong>.</li>
                  <li>Change <strong>Notifications</strong> to <em>Allow</em>.</li>
                  <li>Return here and click <em>Recheck Permission</em>.</li>
                </ol>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // 4. PERMISSION DEFAULT / NOT YET REQUESTED
  return (
    <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-xs space-y-2.5">
      <div className="flex items-start gap-2">
        <div className="w-7 h-7 rounded-lg bg-blue-100 flex items-center justify-center text-blue-700 shrink-0 mt-0.5">
          <Bell className="w-4 h-4" />
        </div>
        <div>
          <div className="font-bold text-blue-950 text-xs">Desktop Notifications Inactive</div>
          <p className="text-[11px] text-blue-800 mt-0.5 leading-relaxed">
            Enable browser notifications to receive real-time Windows desktop alerts when your
            configured threshold is exceeded.
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={onRequestPermission}
        className="w-full py-1.5 px-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs flex items-center justify-center gap-1.5 shadow-2xs transition"
      >
        <Bell className="w-3.5 h-3.5" />
        <span>Enable Desktop Notifications</span>
      </button>
    </div>
  );
};
