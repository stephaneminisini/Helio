const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export interface ComparisonPair {
  current_kwh: number;
  prior_kwh: number | null;
  pct_change: number | null;
}

export interface OverviewData {
  today: string;
  today_kwh: number;
  current_power_w: number | null;
  day_comparison: ComparisonPair;
  month_comparison: ComparisonPair;
  ytd_comparison: ComparisonPair;
  best_day_kwh: number | null;
  best_day_date: string | null;
  all_time_kwh: number;
}

export interface MonthlyPRPoint {
  month: string;
  production_kwh: number;
  performance_ratio: number | null;
  expected_pr: number | null;
  is_anomaly: boolean;
}

export interface EfficiencyData {
  pr_history: MonthlyPRPoint[];
  degradation: {
    annual_rates: Record<string, { avg_pr: number; annual_drop: number | null }>;
    lost_kwh: number;
    lost_dollars: number;
    warranty_threshold: number;
    exceeds_warranty: boolean;
  };
}

export interface SystemSettings {
  enphase_system_id: string;
  name: string | null;
  location: string | null;
  latitude: string | null;
  longitude: string | null;
  system_size_kw: string | null;
  panel_count: number | null;
  panel_wattage_w: number | null;
  install_date: string;
  tilt_angle_deg: string | null;
  azimuth_deg: string | null;
  degradation_rate: string;
  irradiance_source: string;
}

/** Fields the Setup form can send. Null clears a value. */
export type SettingsPayload = {
  [K in keyof SystemSettings]?: SystemSettings[K] | null;
};

/** A create payload; the API requires these two fields. */
export interface NewSystemPayload extends SettingsPayload {
  enphase_system_id: string;
  install_date: string;
}

/** Carries the HTTP status so callers can tell 404 apart from a real failure. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `API error ${response.status}: ${await response.text()}`
    );
  }
  return response.json() as Promise<T>;
}

export const api = {
  getOverview: () => apiFetch<OverviewData>("/api/overview"),
  getEfficiency: () => apiFetch<EfficiencyData>("/api/efficiency"),
  getSettings: () => apiFetch<SystemSettings>("/api/settings"),
  createSettings: (data: NewSystemPayload) =>
    apiFetch<SystemSettings>("/api/settings", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateSettings: (data: SettingsPayload) =>
    apiFetch<SystemSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
};
