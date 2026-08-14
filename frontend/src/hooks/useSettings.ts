import { useEffect, useState } from "react";
import {
  ApiError,
  NewSystemPayload,
  SettingsPayload,
  SystemSettings,
  api,
} from "../api/client";

export function useSettings() {
  const [data, setData] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function save(updates: SettingsPayload): Promise<SystemSettings> {
    const updated = await api.updateSettings(updates);
    setData(updated);
    return updated;
  }

  async function create(payload: NewSystemPayload): Promise<SystemSettings> {
    const created = await api.createSettings(payload);
    setData(created);
    return created;
  }

  useEffect(() => {
    api
      .getSettings()
      .then(setData)
      .catch((e: Error) => {
        // A 404 means nothing has been configured yet, which is the onboarding
        // path rather than a failure. Every other status is a real error.
        if (e instanceof ApiError && e.status === 404) return;
        setError(e.message);
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error, save, create };
}
