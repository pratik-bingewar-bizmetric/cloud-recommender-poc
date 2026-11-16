import { useCallback, useState } from "react";

import { missingEntraSettings } from "@/config/entra";
import { useAzureLiveConnection } from "@/hooks/use-azure-live-connection";
import type { AzureLiveApi } from "@/lib/azureLiveApi";
import { entraTokenService, type BackendTokenService } from "@/services/entra-token.service";
import { AzureConnectionForm } from "./AzureConnectionForm";
import { AzureLiveDashboard } from "./AzureLiveDashboard";

interface Props {
  api?: AzureLiveApi;
  tokenService?: BackendTokenService;
}

/** Live Azure connection screen: API sign-in -> service principal -> real Azure data. */
export function AzureLiveView({ api, tokenService = entraTokenService }: Props) {
  const live = useAzureLiveConnection(api);
  const [apiSignedIn, setApiSignedIn] = useState<boolean>(() => tokenService.getAccount() !== null);
  const [signInError, setSignInError] = useState<string | null>(null);

  const configured = tokenService.isConfigured();

  const signIn = useCallback(async () => {
    setSignInError(null);
    try {
      await tokenService.signIn();
      setApiSignedIn(true);
    } catch (err) {
      setSignInError(err instanceof Error ? err.message : "Sign-in failed.");
    }
  }, [tokenService]);

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4" data-testid="azure-live-view">
      <header>
        <h1 className="text-lg font-bold text-navy-900">Azure Live Connection</h1>
        <p className="text-xs text-slate-600">
          See real subscriptions, resources, metrics and costs from your own Azure account.
        </p>
      </header>

      {!configured && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900" role="alert">
          Application sign-in is not configured for this build. Set {missingEntraSettings().join(", ")} (see the
          deployment report) and rebuild. The backend rejects unauthenticated requests, so data cannot be loaded
          without it.
        </div>
      )}

      {configured && !apiSignedIn && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
          <h2 className="text-sm font-bold text-navy-900">Step 1: Sign in to the Cloud Recommender API</h2>
          <p className="text-xs text-slate-600">
            Sign in with your Microsoft work account so the backend can verify who you are.
          </p>
          <button
            type="button"
            onClick={signIn}
            className="rounded-md bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white"
          >
            Sign in with Microsoft
          </button>
          {signInError && (
            <p className="text-xs text-red-700" role="alert">
              {signInError}
            </p>
          )}
        </div>
      )}

      {configured && apiSignedIn && (
        <>
          {live.error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800" role="alert" data-testid="connect-error">
              <strong>{live.error.message}</strong>
              {live.error.category && <span> ({live.error.category.replace(/_/g, " ")})</span>}
              {live.error.retryAfterSeconds && <span> Retry in {live.error.retryAfterSeconds}s.</span>}
            </div>
          )}

          <AzureConnectionForm
            busy={live.status === "connecting"}
            connected={live.status === "connected"}
            onConnect={live.connect}
            onValidate={live.validate}
            onFetchSubscriptions={live.fetchSubscriptions}
            onDisconnect={live.disconnect}
          />

          {live.status === "connected" && live.connection && (
            <AzureLiveDashboard
              connection={live.connection}
              subscriptions={live.subscriptions}
              selectedSubscriptionId={live.selectedSubscriptionId}
              overview={live.overview}
              loading={live.overviewLoading}
              validation={live.validation}
              selectedResource={live.selectedResource}
              metricDefinitions={live.metricDefinitions}
              metricValues={live.metricValues}
              onSelectSubscription={live.selectSubscription}
              onRefresh={live.refresh}
              onSelectResource={live.selectResource}
              onLoadMetricValues={live.loadMetricValues}
            />
          )}
        </>
      )}
    </div>
  );
}
