import { useEffect, useState } from "react";
import { api, SystemSettings } from "../api/client";

export function useSettings() {
  const [data, setData] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function save(updates: Partial<SystemSettings>): Promise<SystemSettings> {
    const updated = await api.updateSettings(updates);
    setData(updated);
    return updated;
  }

  useEffect(() => {
    api
      .getSettings()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error, save };
}
