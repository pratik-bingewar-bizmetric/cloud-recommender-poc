"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  DatabricksConnection,
  DatabricksConnectionHealth,
  DatabricksWorkspaceDiscovery,
} from "@/types";
import {
  getWorkspaceDiscovery,
  getWorkspaceHealth,
  listDatabricksConnections,
  refreshWorkspaceDiscovery,
} from "@/lib/api";
import { ConnectionView, deriveConnectionView } from "@/lib/connectionState";
import {
  DEFAULT_METADATA_REFRESH_MS,
  DEFAULT_OPERATIONAL_REFRESH_MS,
  createRefreshController,
} from "@/lib/refreshScheduler";

const envMs = (name: string | undefined, fallback: number): number => {
  const n = Number(name);
  return Number.isFinite(n) && n >= 5_000 ? n : fallback;
};

/** Operational refresh (health + inventory). Configurable via NEXT_PUBLIC_REFRESH_INTERVAL_MS. */
export const OPERATIONAL_REFRESH_MS = envMs(
  process.env.NEXT_PUBLIC_REFRESH_INTERVAL_MS,
  DEFAULT_OPERATIONAL_REFRESH_MS
);
/** Slower-changing metadata (connection registry). */
export const METADATA_REFRESH_MS = envMs(
  process.env.NEXT_PUBLIC_METADATA_REFRESH_INTERVAL_MS,
  DEFAULT_METADATA_REFRESH_MS
);

export interface DatabricksConnectionHandle {
  connections: DatabricksConnection[];
  /** Connection selected for the requested workspace (null until the registry loads). */
  connectionId: string | null;
  health: DatabricksConnectionHealth | null;
  discovery: DatabricksWorkspaceDiscovery | null;
  /** The ONLY connection state any component may render. */
  view: ConnectionView;
  isRefreshing: boolean;
  /** Last successful retrieval (ms since epoch) of health+inventory in this browser session. */
  lastSuccessAt: number | null;
  error: string | null;
  /** Manual refresh. `force` re-runs live discovery on the backend instead of reading its cache. */
  refresh: (force?: boolean) => Promise<void>;
}

/**
 * Owns the selected Databricks workspace's connection state, health and inventory.
 * - Fetches only through the backend (no credentials in the browser).
 * - Single-flight refresh on an interval, on manual refresh and when the workspace changes.
 * - Data from a previously selected workspace is cleared immediately (never shown as current).
 * - A failed refresh keeps the last good data but marks it stale via `view.stale`.
 */
export const useDatabricksConnection = (
  workspaceIdOrConnectionId: string | null | undefined
): DatabricksConnectionHandle => {
  const [connections, setConnections] = useState<DatabricksConnection[]>([]);
  const [registryLoaded, setRegistryLoaded] = useState(false);
  const [health, setHealth] = useState<DatabricksConnectionHealth | null>(null);
  const [discovery, setDiscovery] = useState<DatabricksWorkspaceDiscovery | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null);

  const connectionId = useMemo(() => {
    if (!registryLoaded || connections.length === 0) return null;
    const match = connections.find(
      (c) => c.workspace_id === workspaceIdOrConnectionId || c.connection_id === workspaceIdOrConnectionId
    );
    if (match) return match.connection_id;
    return (connections.find((c) => c.status === "connected") ?? connections[0]).connection_id;
  }, [connections, registryLoaded, workspaceIdOrConnectionId]);

  const forceRef = useRef(false);
  const idRef = useRef<string | null>(null);
  idRef.current = connectionId;

  const controller = useMemo(
    () =>
      createRefreshController(
        async () => {
          const id = idRef.current;
          if (!id) return;
          const force = forceRef.current;
          forceRef.current = false;
          setIsRefreshing(true);
          try {
            const [disc, h] = await Promise.all([
              force ? refreshWorkspaceDiscovery(id) : getWorkspaceDiscovery(id),
              getWorkspaceHealth(id),
            ]);
            if (idRef.current !== id) return; // workspace changed while in flight: drop result
            setDiscovery(disc);
            setHealth(h);
            setError(null);
            setLastSuccessAt(Date.now());
          } catch (err) {
            if (idRef.current === id) {
              setError(err instanceof Error ? err.message : "Databricks health request failed.");
            }
            throw err;
          } finally {
            setLoading(false);
            setIsRefreshing(false);
          }
        },
        { staleAfterMs: OPERATIONAL_REFRESH_MS * 3 }
      ),
    []
  );

  // Registry (slow-changing): on mount and on the metadata interval
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const conns = await listDatabricksConnections();
        if (alive) {
          setConnections(conns);
          setRegistryLoaded(true);
        }
      } catch (err) {
        if (alive) {
          setError(err instanceof Error ? err.message : "Databricks connection registry unavailable.");
          setRegistryLoaded(true);
          setLoading(false);
        }
      }
    };
    load();
    const t = setInterval(load, METADATA_REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  // Workspace change: clear previous workspace data, then fetch immediately
  useEffect(() => {
    setHealth(null);
    setDiscovery(null);
    setError(null);
    setLastSuccessAt(null);
    if (connectionId) {
      setLoading(true);
      void controller.run();
    } else if (registryLoaded) {
      setLoading(false);
    }
  }, [connectionId, registryLoaded, controller]);

  // Interval refresh (paused while the tab is hidden; refreshes on return)
  useEffect(() => {
    if (!connectionId) return;
    const tick = () => {
      if (typeof document === "undefined" || document.visibilityState === "visible") void controller.run();
    };
    const t = setInterval(tick, OPERATIONAL_REFRESH_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [connectionId, controller]);

  const refresh = useCallback(
    async (force = false) => {
      forceRef.current = force;
      await controller.run();
    },
    [controller]
  );

  const view = useMemo(
    () =>
      deriveConnectionView({
        health,
        loading: loading && !health,
        requestError: error,
        notConfigured: registryLoaded && connections.length === 0,
      }),
    [health, loading, error, registryLoaded, connections.length]
  );

  return { connections, connectionId, health, discovery, view, isRefreshing, lastSuccessAt, error, refresh };
};
