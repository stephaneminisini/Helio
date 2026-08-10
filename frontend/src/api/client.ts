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

export interface NewSystemSettings {
  enphase_system_id: string;
  install_date: string;
  latitude: string;
  longitude: string;
  name?: string | null;
  location?: string | null;
  system_size_kw?: string | null;
  panel_count?: number | null;
  panel_wattage_w?: number | null;
  tilt_angle_deg?: string | null;
  azimuth_deg?: string | null;
  degradation_rate?: string | null;
  irradiance_source?: string | null;
}

export interface PollLogEntry {
  poll_type: string | null;
  status: string | null;
  started_at: string;
  completed_at: string | null;
  records_inserted: number;
  error_message: string | null;
}

export interface BackfillStatus {
  running: boolean;
  total_days: number;
  completed_days: number;
  failed_days: number;
  error: string | null;
}

export interface StatusData {
  configured: boolean;
  location_configured: boolean;
  install_date: string | null;
  first_day: string | null;
  last_day: string | null;
  days_with_data: number;
  days_expected: number;
  missing_days: number;
  months_with_data: number;
  irradiance_source: string | null;
  weather_normalized: boolean;
  last_poll: PollLogEntry | null;
  backfill: BackfillStatus;
}

/** An API failure carrying the HTTP status, so callers can branch on it. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface ValidationDetail {
  loc?: unknown[];
  msg?: string;
}

async function readErrorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const body = JSON.parse(raw) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) => {
          const entry = item as ValidationDetail;
          const field = Array.isArray(entry.loc)
            ? String(entry.loc[entry.loc.length - 1])
            : "";
          const message = entry.msg ?? "is invalid";
          return field ? `${field}: ${message}` : message;
        })
        .join("; ");
    }
  } catch {
    // Not a JSON error envelope - fall through to the raw body.
  }
  return raw || `Request failed with status ${response.status}`;
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError(
      "Cannot reach the Helio API. Check that the backend container is running.",
      0
    );
  }
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  getOverview: () => apiFetch<OverviewData>("/api/overview"),
  getEfficiency: () => apiFetch<EfficiencyData>("/api/efficiency"),
  getStatus: () => apiFetch<StatusData>("/api/status"),
  getSettings: () => apiFetch<SystemSettings>("/api/settings"),
  createSettings: (data: NewSystemSettings) =>
    apiFetch<SystemSettings>("/api/settings", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateSettings: (data: Partial<SystemSettings>) =>
    apiFetch<SystemSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  startBackfill: () =>
    apiFetch<BackfillStatus>("/api/backfill", { method: "POST" }),
};
