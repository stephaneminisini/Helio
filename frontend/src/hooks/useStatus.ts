import { useCallback, useEffect, useState } from "react";
import { api, StatusData } from "../api/client";

const BACKFILL_POLL_INTERVAL_MS = 2000;

export interface StatusController {
  data: StatusData | null;
  loading: boolean;
  error: string | null;
  starting: boolean;
  startError: string | null;
  refresh: () => Promise<void>;
  startBackfill: () => Promise<void>;
}

export function useStatus(): StatusController {
  const [data, setData] = useState<StatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setData(await api.getStatus());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const startBackfill = useCallback(async () => {
    setStarting(true);
    setStartError(null);
    try {
      const started = await api.startBackfill();
      // Trust the accepted response so polling begins without waiting a tick for
      // the background task to flip the server-side flag.
      setData((prev) => (prev ? { ...prev, backfill: started } : prev));
    } catch (e) {
      setStartError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }, []);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  const running = data?.backfill.running ?? false;

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, BACKFILL_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [running, refresh]);

  return { data, loading, error, starting, startError, refresh, startBackfill };
}
