"use client";

import { useState, useEffect, useCallback } from "react";
import { BrowserPermissionStatus } from "@/types/notifications";
import { BrowserNotificationService } from "./browserNotificationService";

export interface UseNotificationPermissionReturn {
  permission: BrowserPermissionStatus;
  isSupported: boolean;
  isSecure: boolean;
  requestPermission: (onNotificationClick?: () => void) => Promise<BrowserPermissionStatus>;
  refreshPermission: () => BrowserPermissionStatus;
}

export function useNotificationPermission(): UseNotificationPermissionReturn {
  const [permission, setPermission] = useState<BrowserPermissionStatus>("default");
  const [isSupported, setIsSupported] = useState<boolean>(true);
  const [isSecure, setIsSecure] = useState<boolean>(true);

  const refreshPermission = useCallback(() => {
    const supported = BrowserNotificationService.isSupported();
    const secure = BrowserNotificationService.isSecure();
    setIsSupported(supported);
    setIsSecure(secure);

    if (!supported) {
      setPermission("unsupported");
      return "unsupported";
    }

    const current = BrowserNotificationService.getPermission();
    setPermission(current);
    return current;
  }, []);

  useEffect(() => {
    refreshPermission();

    // Recheck permission when browser window regains focus (e.g. after user toggles site settings)
    const handleFocus = () => {
      refreshPermission();
    };

    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("focus", handleFocus);
    };
  }, [refreshPermission]);

  const requestPermission = useCallback(
    async (onNotificationClick?: () => void): Promise<BrowserPermissionStatus> => {
      const result = await BrowserNotificationService.requestPermission();
      setPermission(result);

      if (result === "granted") {
        BrowserNotificationService.sendConfirmation(onNotificationClick);
      }
      return result;
    },
    []
  );

  return {
    permission,
    isSupported,
    isSecure,
    requestPermission,
    refreshPermission,
  };
}

