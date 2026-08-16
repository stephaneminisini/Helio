import { useEffect, useState } from "react";
import { PanelsData, api } from "../api/client";

export function usePanels() {
  const [data, setData] = useState<PanelsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getPanels()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return { data, loading, error };
}
