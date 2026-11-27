"use client";

import React from "react";
import { Bell } from "lucide-react";
import { BrowserPermissionStatus, ThresholdStatus } from "@/types/notifications";

interface FloatingNotificationButtonProps {
  isOpen: boolean;
  permission: BrowserPermissionStatus;
  thresholdStatus: ThresholdStatus;
  notificationCount: number;
  onClick: () => void;
}

export const FloatingNotificationButton: React.FC<FloatingNotificationButtonProps> = ({
  isOpen,
  permission,
  thresholdStatus,
  notificationCount,
  onClick,
}) => {
  // If panel is already open and not minimized, button is hidden or styled as active
  if (isOpen) return null;

  const getBadge = () => {
    if (thresholdStatus === "EXCEEDED") {
      return (
        <span className="absolute -top-1 -right-1 flex h-4 w-4">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-4 w-4 bg-rose-500 text-[9px] text-white font-bold items-center justify-center">
            !
          </span>
        </span>
      );
    }
    if (permission === "default") {
      return (
        <span
          className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-blue-500 border-2 border-white"
          title="Notification permission not requested"
        />
      );
    }
    if (permission === "denied") {
      return (
        <span
          className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-amber-500 border-2 border-white"
          title="Notifications blocked"
        />
      );
    }
    if (notificationCount > 0) {
      return (
        <span className="absolute -top-1 -right-1 px-1 min-w-[16px] h-4 rounded-full bg-brand-600 text-[10px] text-white font-mono font-bold flex items-center justify-center border-2 border-white">
          {notificationCount}
        </span>
      );
    }
    return null;
  };

  return (
    <button
      type="button"
      onClick={onClick}
      className="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-full bg-navy-950 text-white shadow-xl hover:bg-navy-900 hover:scale-105 active:scale-95 border border-slate-700 flex items-center justify-center transition-all duration-200 group focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
      title="Open FinOps Notification Simulator"
      aria-label="Open FinOps Notification Simulator"
    >
      <div className="relative">
        <Bell className="w-5 h-5 text-amber-400 group-hover:rotate-12 transition-transform duration-200" />
        {getBadge()}
      </div>
    </button>
  );
};
