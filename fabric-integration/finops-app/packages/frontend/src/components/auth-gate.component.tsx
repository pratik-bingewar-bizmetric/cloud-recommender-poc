//-----------------------------------------------------------------------
// <copyright company="Microsoft Corporation">
//        Copyright (c) Microsoft Corporation.  All rights reserved.
//        Licensed under the MIT license. See LICENSE file in the project root for full license information.
// </copyright>
//-----------------------------------------------------------------------

import { useEffect, useState, type ReactNode } from "react";
import { CloudLoginForm } from "./CloudLoginForm";
import { getSessionInfo, getSessionToken, setSessionToken } from "@/lib/api";
import type { ServicePrincipalConnectResponse, SessionInfoResponse } from "@/types/auth";
import { useAuth } from "@/hooks/auth.context";

interface AuthGateProps {
  children: ReactNode;
}

/**
 * Service Principal Application Auth Gate.
 * Enforces Service Principal-only authentication before presenting the FinOps dashboard,
 * while maintaining compatibility with Fabric host session resolution.
 */
export function AuthGate({ children }: AuthGateProps) {
  const {
    isLoading: isRayfinLoading,
    isAuthenticated: isRayfinAuthenticated,
    canSignIn,
    signIn,
    isSigningIn,
    signInError,
    config,
    error,
  } = useAuth();

  const [activeSession, setActiveSession] = useState<
    ServicePrincipalConnectResponse | SessionInfoResponse | null
  >(null);
  const [isCheckingSession, setIsCheckingSession] = useState<boolean>(
    () => typeof window !== "undefined" && Boolean(getSessionToken())
  );

  useEffect(() => {
    let cancelled = false;

    const token = getSessionToken();
    if (!token) {
      return;
    }

    getSessionInfo()
      .then((session) => {
        if (!cancelled) {
          setActiveSession(session);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSessionToken(null);
          setActiveSession(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsCheckingSession(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (isRayfinLoading || isCheckingSession) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-sm text-muted-foreground">
          Connecting to Fabric…
        </div>
      </div>
    );
  }

  // Handle configuration issues from Fabric host if reported
  if (config.kind === "not-deployed") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <div className="w-full max-w-md text-center">
          <h2 className="mb-2 text-lg font-semibold text-foreground">
            Configure this app to sign in
          </h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Signing in needs a Fabric backend. Start{" "}
            <code className="rounded bg-muted px-1 py-0.5">npm run dev</code>{" "}
            with an approved workspace, or deploy this app, then reload.
          </p>
        </div>
      </div>
    );
  }

  if (config.kind === "incomplete") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <div className="w-full max-w-md text-center">
          <h2 className="mb-2 text-lg font-semibold text-foreground">
            This app is missing its Rayfin configuration
          </h2>
          <p className="mb-4 text-sm text-muted-foreground">
            The dev server started without {config.missing.join(", ")}. Check
            the warnings it printed, then restart it.
          </p>
        </div>
      </div>
    );
  }

  if (config.kind === "config-error") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <div className="w-full max-w-md text-center">
          <h2 className="mb-2 text-lg font-semibold text-foreground">
            Couldn't load this app's configuration
          </h2>
          <p className="mb-4 text-sm text-muted-foreground">
            The app stopped rather than fall back to the values it was built
            with, which in a promoted environment point at the wrong backend.
            Redeploy this stage, then reload.
          </p>
          <p className="text-xs text-muted-foreground">{config.message}</p>
        </div>
      </div>
    );
  }

  // Authenticated state: Either active Service Principal session or authenticated Rayfin session
  if (isRayfinAuthenticated || activeSession) {
    return <>{children}</>;
  }

  // Unauthenticated: Present the dedicated enterprise Service Principal Cloud Login form
  return (
    <CloudLoginForm
      onSuccess={(session) => setActiveSession(session)}
      canSignIn={canSignIn}
      onSignInWithMicrosoft={signIn}
      isSigningIn={isSigningIn}
      signInError={signInError}
      authError={error}
    />
  );
}
