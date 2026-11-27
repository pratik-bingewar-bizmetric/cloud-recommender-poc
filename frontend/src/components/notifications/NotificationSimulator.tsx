"use client";

import React, { useState, useCallback } from "react";
import { useNotificationPermission } from "@/lib/notifications/useNotificationPermission";
import { useThresholdSimulation } from "@/lib/notifications/useThresholdSimulation";
import { FloatingNotificationButton } from "./FloatingNotificationButton";
import { NotificationSimulatorPanel } from "./NotificationSimulatorPanel";

export const NotificationSimulator: React.FC = () => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [isMinimized, setIsMinimized] = useState<boolean>(false);

  // Callback when user clicks a native desktop notification banner
  const handleNotificationClick = useCallback(() => {
    setIsOpen(true);
    setIsMinimized(false);
  }, []);

  // Permission hook
  const {
    permission,
    isSupported,
    isSecure,
    requestPermission,
    refreshPermission,
  } = useNotificationPermission();

  // Threshold simulation hook
  const {
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
  } = useThresholdSimulation({
    permission,
    onNotificationClick: handleNotificationClick,
  });

  const handleToggleOpen = () => {
    setIsOpen((prev) => !prev);
    setIsMinimized(false);
  };

  const handleMinimize = () => {
    setIsMinimized((prev) => !prev);
  };

  const handleClose = () => {
    setIsOpen(false);
    setIsMinimized(false);
  };

  return (
    <>
      {/* Floating Circular Chatbot-style Button */}
      <FloatingNotificationButton
        isOpen={isOpen && !isMinimized}
        permission={permission}
        thresholdStatus={thresholdStatus}
        notificationCount={notificationCount}
        onClick={handleToggleOpen}
      />

      {/* Floating Simulation Panel */}
      <NotificationSimulatorPanel
        isOpen={isOpen}
        isMinimized={isMinimized}
        threshold={threshold}
        simulatedValue={simulatedValue}
        thresholdStatus={thresholdStatus}
        isArmed={isArmed}
        permission={permission}
        isSupported={isSupported}
        isSecure={isSecure}
        notificationCount={notificationCount}
        lastAttemptTime={lastAttemptTime}
        lastAttemptResult={lastAttemptResult}
        history={history}
        inAppAlertMessage={inAppAlertMessage}
        onClose={handleClose}
        onMinimize={handleMinimize}
        onThresholdChange={setThreshold}
        onIncrementThreshold={incrementThreshold}
        onDecrementThreshold={decrementThreshold}
        onSliderChange={handleSliderChange}
        onRequestPermission={() => requestPermission(handleNotificationClick)}
        onRefreshPermission={refreshPermission}
        onSendTestNotification={sendTestAlert}
        onResetSimulator={resetSimulator}
        onClearHistory={clearHistory}
        onDismissInAppAlert={dismissInAppAlert}
      />
    </>
  );
};

