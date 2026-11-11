"use client";

import React, { useEffect, useState } from "react";
import { globalLoadingManager, GlobalLoadingState } from "@/lib/loadingManager";

export const TopLoadingProgressBar: React.FC = () => {
  const [state, setState] = useState<GlobalLoadingState>(() => globalLoadingManager.getState());
  const [visible, setVisible] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0);

  useEffect(() => {
    return globalLoadingManager.subscribe((newState) => {
      setState(newState);
      if (newState.isLoading) {
        setVisible(true);
        setProgress((prev) => (prev === 0 ? 25 : Math.min(prev + 15, 85)));
      } else if (!newState.isError) {
        // Complete smoothly
        setProgress(100);
        const timer = setTimeout(() => {
          setVisible(false);
          setProgress(0);
        }, 400);
        return () => clearTimeout(timer);
      }
    });
  }, []);

  // Increment simulated progress while loading
  useEffect(() => {
    if (!state.isLoading) return;
    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 85) return prev;
        return prev + (90 - prev) * 0.15;
      });
    }, 300);
    return () => clearInterval(interval);
  }, [state.isLoading]);

  if (!visible && !state.isError) return null;

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 h-[3px] pointer-events-none overflow-hidden bg-transparent"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(progress)}
    >
      <div
        className={`h-full transition-all duration-300 ease-out shadow-sm ${
          state.isError
            ? "bg-rose-500 w-full"
            : "bg-gradient-to-r from-blue-500 via-brand-600 to-indigo-600 shadow-[0_0_8px_rgba(37,99,235,0.6)]"
        }`}
        style={{
          width: state.isError ? "100%" : `${progress}%`,
          opacity: visible || state.isError ? 1 : 0,
        }}
      />
    </div>
  );
};

