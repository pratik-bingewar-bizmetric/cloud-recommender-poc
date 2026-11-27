"use client";

import React from "react";
import { History, Trash2, CheckCircle2, AlertTriangle, XCircle, Bell } from "lucide-react";
import { NotificationHistoryItem, SimulatorEventType } from "@/types/notifications";

interface NotificationHistoryProps {
  history: NotificationHistoryItem[];
  onClearHistory: () => void;
}

export const NotificationHistory: React.FC<NotificationHistoryProps> = ({
  history,
  onClearHistory,
}) => {
  const getEventBadge = (type: SimulatorEventType) => {
    switch (type) {
      case "THRESHOLD_EXCEEDED":
        return {
          icon: <AlertTriangle className="w-3 h-3 text-rose-500" />,
          label: "Threshold Exceeded",
          bg: "bg-rose-50 text-rose-700 border-rose-200",
        };
      case "TEST_NOTIFICATION":
        return {
          icon: <Bell className="w-3 h-3 text-blue-500" />,
          label: "Test Alert",
          bg: "bg-blue-50 text-blue-700 border-blue-200",
        };
      case "PERMISSION_GRANTED":
      case "CONFIRMATION_NOTIFICATION":
        return {
          icon: <CheckCircle2 className="w-3 h-3 text-emerald-500" />,
          label: "Permitted",
          bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
        };
      case "NOTIFICATION_BLOCKED":
      case "PERMISSION_DENIED":
      case "NOTIFICATION_REQUEST_FAILED":
      default:
        return {
          icon: <XCircle className="w-3 h-3 text-amber-500" />,
          label: "Blocked / Failed",
          bg: "bg-amber-50 text-amber-700 border-amber-200",
        };
    }
  };

  return (
    <div className="space-y-2 pt-1 border-t border-slate-100">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 font-bold text-slate-700">
          <History className="w-3.5 h-3.5 text-slate-500" />
          <span>Notification Event History</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-100 text-slate-600 font-mono">
            {history.length}
          </span>
        </div>
        {history.length > 0 && (
          <button
            type="button"
            onClick={onClearHistory}
            className="text-[11px] text-slate-400 hover:text-slate-600 flex items-center gap-1 transition"
            title="Clear History"
          >
            <Trash2 className="w-3 h-3" />
            <span>Clear</span>
          </button>
        )}
      </div>

      <div className="max-h-36 overflow-y-auto space-y-1.5 pr-0.5">
        {history.length === 0 ? (
          <div className="py-4 text-center bg-slate-50 border border-dashed border-slate-200 rounded-lg text-slate-400 text-[11px]">
            No simulation events logged yet. Drag slider past threshold to trigger.
          </div>
        ) : (
          history.map((item) => {
            const badge = getEventBadge(item.eventType);
            return (
              <div
                key={item.id}
                className="p-2 bg-slate-50 border border-slate-200 rounded-lg text-[11px] space-y-1"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    {badge.icon}
                    <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold border ${badge.bg}`}>
                      {badge.label}
                    </span>
                  </div>
                  <span className="font-mono text-[10px] text-slate-400">
                    {item.timeFormatted}
                  </span>
                </div>
                <div className="flex items-center justify-between text-slate-600 text-[10px] font-mono pt-0.5">
                  <span>
                    Value: <strong>{item.simulatedValue}%</strong> (Thresh: {item.threshold}%)
                  </span>
                  <span className={item.result === "NATIVE_SUCCESS" ? "text-emerald-700 font-semibold" : "text-amber-700 font-semibold"}>
                    {item.result === "NATIVE_SUCCESS" ? "Delivered to OS" : item.result}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

