import { useEffect, useState } from "react";
import { ApiError, NewSystemSettings, SystemSettings, api } from "../api/client";

export function useSettings() {
  const [data, setData] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function save(updates: Partial<SystemSettings>): Promise<SystemSettings> {
    const updated = await api.updateSettings(updates);
    setData(updated);
    return updated;
  }

  async function create(payload: NewSystemSettings): Promise<SystemSettings> {
    const created = await api.createSettings(payload);
    setData(created);
    return created;
  }

  useEffect(() => {
    api
      .getSettings()
      .then(setData)
      .catch((e: Error) => {
        // A 404 means no system exists yet - that is first run, not a failure.
        if (e instanceof ApiError && e.status === 404) return;
        setError(e.message);
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error, save, create };
}
