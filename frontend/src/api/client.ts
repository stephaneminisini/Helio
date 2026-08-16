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
  day_vs_last_month: ComparisonPair;
  month_comparison: ComparisonPair;
  month_vs_last_year: ComparisonPair;
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
  /** The summarizer's explanation of the flag; null when is_anomaly is false. */
  anomaly_reason: string | null;
}

/** One projected calendar year, valued at the year's mid-point. */
export interface ProjectedYear {
  year: number;
  projected_pr: number;
}

export interface ProjectionSummary {
  months_of_history: number;
  /** PR fraction lost per year by the fitted trend; null when no fit is possible. */
  annual_rate: number | null;
  low_confidence: boolean;
  warranty_breach_year: number | null;
  years: ProjectedYear[];
}

export interface EfficiencyData {
  pr_history: MonthlyPRPoint[];
  projection: ProjectionSummary;
  degradation: {
    annual_rates: Record<string, { avg_pr: number; annual_drop: number | null }>;
    lost_kwh: number;
    lost_dollars: number;
    warranty_threshold: number;
    exceeds_warranty: boolean;
    energy_rate_per_kwh: number;
    energy_rate_currency: string;
  };
}

/** One panel's production over the window, relative to the rest of the fleet. */
export interface PanelPoint {
  panel_serial: string;
  energy_wh: number;
  /** Production as a fraction of the fleet average, so 1.0 is average. */
  normalized_efficiency: number;
  /** Null when the fleet is too small or too uniform to measure a spread. */
  deviation_sigma: number | null;
  is_underperforming: boolean;
}

export interface PanelsData {
  panels: PanelPoint[];
  fleet_average_wh: number;
  fleet_stdev_wh: number;
  window_start: string;
  window_end: string;
  /** False when there is nothing to plot; unavailable_reason says why. */
  data_available: boolean;
  unavailable_reason: string | null;
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
  warranty_degradation_rate: string;
  energy_rate_per_kwh: string;
  energy_rate_currency: string;
  irradiance_source: string;
  enphase_connected: boolean;
}

/** Enphase connection state. Holds no token or secret by design. */
export interface EnphaseStatus {
  connected: boolean;
  client_configured: boolean;
  token_updated_at: string | null;
  last_successful_poll_at: string | null;
  token_warning: string | null;
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
  getPanels: () => apiFetch<PanelsData>("/api/panels"),
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
  getEnphaseStatus: () => apiFetch<EnphaseStatus>("/api/auth/enphase/status"),
  getEnphaseConsentUrl: () =>
    apiFetch<{ authorization_url: string }>("/api/auth/enphase/authorize"),
};
