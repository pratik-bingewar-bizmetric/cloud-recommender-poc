/**
 * State for the live Azure connection screen.
 *
 * The service principal secret is kept ONLY in a React ref (memory) so the session can be
 * re-established if the backend's short-lived token expires. It is wiped on disconnect and is
 * never written to browser storage, a URL, a log or application state that is rendered.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { AzureLiveApiError, azureLiveApi, type AzureLiveApi } from "@/lib/azureLiveApi";
import type {
  AzureConnectionInfo,
  AzureCredentials,
  AzureResource,
  AzureSubscription,
  DataDomain,
  MetricDefinition,
  MetricSeries,
  OverviewResponse,
} from "@/types/azureLive";

export type ConnectionStatus = "disconnected" | "connecting" | "connected";

export interface UiError {
  code: string;
  message: string;
  category?: string;
  retryAfterSeconds?: number;
}

function toUiError(error: unknown): UiError {
  if (error instanceof AzureLiveApiError) {
    return {
      code: error.code,
      message: error.message,
      category: error.category,
      retryAfterSeconds: error.retryAfterSeconds,
    };
  }
  return {
    code: "unexpected_error",
    message: error instanceof Error ? error.message : "An unexpected error occurred.",
  };
}

function firstAccessible(domain: DataDomain<AzureSubscription> | null): string | null {
  const item = domain?.items?.find((s) => s.state === "Enabled") ?? domain?.items?.[0];
  return item?.subscription_id ?? null;
}

export function useAzureLiveConnection(api: AzureLiveApi = azureLiveApi) {
  const credentialsRef = useRef<AzureCredentials | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [error, setError] = useState<UiError | null>(null);
  const [connection, setConnection] = useState<AzureConnectionInfo | null>(null);
  const [subscriptions, setSubscriptions] = useState<DataDomain<AzureSubscription> | null>(null);
  const [requestedSubscription, setRequestedSubscription] =
    useState<DataDomain<AzureSubscription> | null>(null);
  const [selectedSubscriptionId, setSelectedSubscriptionId] = useState<string | null>(null);
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [selectedResource, setSelectedResource] = useState<AzureResource | null>(null);
  const [metricDefinitions, setMetricDefinitions] = useState<DataDomain<MetricDefinition> | null>(null);
  const [metricValues, setMetricValues] = useState<DataDomain<MetricSeries> | null>(null);
  const [validation, setValidation] = useState<{ valid: boolean; checkedAt: string } | null>(null);

  // Wipe the in-memory secret if the screen is torn down.
  useEffect(
    () => () => {
      credentialsRef.current = null;
    },
    [],
  );

  const reset = useCallback(() => {
    credentialsRef.current = null;
    setStatus("disconnected");
    setConnection(null);
    setSubscriptions(null);
    setRequestedSubscription(null);
    setSelectedSubscriptionId(null);
    setOverview(null);
    setSelectedResource(null);
    setMetricDefinitions(null);
    setMetricValues(null);
    setValidation(null);
  }, []);

  /** Runs a call; if the backend forgot the connection, reconnects once with the in-memory secret. */
  const withReconnect = useCallback(
    async <T,>(
      connectionId: string,
      run: (id: string) => Promise<T>,
    ): Promise<{ value: T; connectionId: string }> => {
      try {
        return { value: await run(connectionId), connectionId };
      } catch (err) {
        const creds = credentialsRef.current;
        if (err instanceof AzureLiveApiError && err.isConnectionGone && creds) {
          const response = await api.connect(creds);
          setConnection(response.connection);
          setSubscriptions(response.subscriptions);
          return {
            value: await run(response.connection.connection_id),
            connectionId: response.connection.connection_id,
          };
        }
        throw err;
      }
    },
    [api],
  );

  const loadOverview = useCallback(
    async (connectionId: string, subscriptionId: string) => {
      setOverviewLoading(true);
      setError(null);
      try {
        const { value } = await withReconnect(connectionId, (id) => api.overview(id, subscriptionId));
        setOverview(value);
        setSelectedSubscriptionId(subscriptionId);
        setSelectedResource(null);
        setMetricDefinitions(null);
        setMetricValues(null);
      } catch (err) {
        const ui = toUiError(err);
        if (err instanceof AzureLiveApiError && err.isConnectionGone) reset();
        setError(ui);
      } finally {
        setOverviewLoading(false);
      }
    },
    [api, reset, withReconnect],
  );

  const connect = useCallback(
    async (credentials: AzureCredentials) => {
      setStatus("connecting");
      setError(null);
      try {
        const response = await api.connect(credentials);
        credentialsRef.current = credentials;
        setConnection(response.connection);
        setSubscriptions(response.subscriptions);
        setRequestedSubscription(response.requested_subscription);
        setStatus("connected");
        const requested =
          response.requested_subscription?.state === "accessible"
            ? credentials.subscriptionId?.trim() || null
            : null;
        const target = requested ?? firstAccessible(response.subscriptions);
        if (target) await loadOverview(response.connection.connection_id, target);
      } catch (err) {
        credentialsRef.current = null;
        setStatus("disconnected");
        setError(toUiError(err));
      }
    },
    [api, loadOverview],
  );

  const validate = useCallback(async () => {
    if (!connection) return;
    setError(null);
    try {
      const { value } = await withReconnect(connection.connection_id, (id) => api.validate(id));
      setConnection(value.connection);
      setSubscriptions(value.subscriptions);
      setValidation({ valid: value.valid, checkedAt: new Date().toISOString() });
    } catch (err) {
      if (err instanceof AzureLiveApiError && err.isConnectionGone) reset();
      setError(toUiError(err));
    }
  }, [api, connection, reset, withReconnect]);

  const fetchSubscriptions = useCallback(async () => {
    if (!connection) return;
    setError(null);
    try {
      const { value } = await withReconnect(connection.connection_id, (id) => api.subscriptions(id));
      setSubscriptions(value);
    } catch (err) {
      if (err instanceof AzureLiveApiError && err.isConnectionGone) reset();
      setError(toUiError(err));
    }
  }, [api, connection, reset, withReconnect]);

  const selectSubscription = useCallback(
    async (subscriptionId: string) => {
      if (connection) await loadOverview(connection.connection_id, subscriptionId);
    },
    [connection, loadOverview],
  );

  const refresh = useCallback(async () => {
    if (!connection || !selectedSubscriptionId) return;
    await fetchSubscriptions();
    await loadOverview(connection.connection_id, selectedSubscriptionId);
  }, [connection, fetchSubscriptions, loadOverview, selectedSubscriptionId]);

  const disconnect = useCallback(async () => {
    const id = connection?.connection_id;
    reset();
    setError(null);
    if (id) {
      try {
        await api.disconnect(id);
      } catch {
        // The local session is already gone; the backend token expires on its own.
      }
    }
  }, [api, connection, reset]);

  const selectResource = useCallback(
    async (resource: AzureResource | null) => {
      setSelectedResource(resource);
      setMetricDefinitions(null);
      setMetricValues(null);
      if (!resource || !connection || !selectedSubscriptionId) return;
      try {
        const { value } = await withReconnect(connection.connection_id, (id) =>
          api.metricDefinitions(id, selectedSubscriptionId, resource.id),
        );
        setMetricDefinitions(value);
      } catch (err) {
        setError(toUiError(err));
      }
    },
    [api, connection, selectedSubscriptionId, withReconnect],
  );

  const loadMetricValues = useCallback(
    async (metricNames: string[]) => {
      if (!connection || !selectedSubscriptionId || !selectedResource || metricNames.length === 0) return;
      try {
        const { value } = await withReconnect(connection.connection_id, (id) =>
          api.metricValues(id, selectedSubscriptionId, selectedResource.id, metricNames),
        );
        setMetricValues(value.metrics);
      } catch (err) {
        setError(toUiError(err));
      }
    },
    [api, connection, selectedResource, selectedSubscriptionId, withReconnect],
  );

  return {
    status,
    error,
    connection,
    subscriptions,
    requestedSubscription,
    selectedSubscriptionId,
    overview,
    overviewLoading,
    selectedResource,
    metricDefinitions,
    metricValues,
    validation,
    connect,
    validate,
    fetchSubscriptions,
    selectSubscription,
    refresh,
    disconnect,
    selectResource,
    loadMetricValues,
    clearError: () => setError(null),
  };
}
