import { useState } from "react";
import { SettingsPayload } from "../api/client";
import { EnphaseConnection } from "../components/EnphaseConnection";
import { useSettings } from "../hooks/useSettings";

/** Fields POST /api/settings rejects with a 422 when they are missing. */
const REQUIRED_TO_CREATE: Record<string, string> = {
  enphase_system_id: "Enphase System ID is required.",
  install_date: "Install date is required.",
};

/** Read a trimmed value, or null when the input was left blank. */
function text(fd: FormData, name: string): string | null {
  return ((fd.get(name) as string | null) ?? "").trim() || null;
}

function integer(fd: FormData, name: string): number | null {
  const value = text(fd, name);
  return value === null ? null : Number(value);
}

/** Collect the editable fields; null clears a value rather than sending "". */
function buildPayload(fd: FormData): SettingsPayload {
  return {
    name: text(fd, "name"),
    location: text(fd, "location"),
    latitude: text(fd, "latitude"),
    longitude: text(fd, "longitude"),
    system_size_kw: text(fd, "system_size_kw"),
    panel_count: integer(fd, "panel_count"),
    panel_wattage_w: integer(fd, "panel_wattage_w"),
    install_date: text(fd, "install_date"),
    tilt_angle_deg: text(fd, "tilt_angle_deg"),
    azimuth_deg: text(fd, "azimuth_deg"),
    degradation_rate: text(fd, "degradation_rate"),
    warranty_degradation_rate: text(fd, "warranty_degradation_rate"),
    energy_rate_per_kwh: text(fd, "energy_rate_per_kwh"),
    baseline_pr: text(fd, "baseline_pr"),
    // The API only accepts an uppercase ISO 4217 code, so "usd" is normalised
    // here rather than coming back as a 422.
    energy_rate_currency: text(fd, "energy_rate_currency")?.toUpperCase() ?? null,
    irradiance_source: text(fd, "irradiance_source"),
  };
}

export function SetupPage() {
  const { data, loading, error, save, create } = useSettings();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  if (loading) return <div className="text-gray-400 p-8">Loading...</div>;
  // A 404 is handled in the hook, so anything here is a real failure.
  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;

  // No system yet: the same form runs in create mode against POST.
  const creating = data === null;

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const payload = buildPayload(fd);
    const enphaseSystemId = text(fd, "enphase_system_id");

    if (creating) {
      const missing: Record<string, string> = {};
      if (!enphaseSystemId) {
        missing.enphase_system_id = REQUIRED_TO_CREATE.enphase_system_id;
      }
      if (!payload.install_date) {
        missing.install_date = REQUIRED_TO_CREATE.install_date;
      }
      if (Object.keys(missing).length > 0) {
        setFieldErrors(missing);
        setSaveError(null);
        return;
      }
    }

    setFieldErrors({});
    setSaving(true);
    setSaveError(null);
    try {
      if (creating) {
        await create({
          ...payload,
          enphase_system_id: enphaseSystemId as string,
          install_date: payload.install_date as string,
        });
      } else {
        await save(payload);
      }
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const field = (
    label: string,
    name: string,
    defaultValue: string | number | null,
    type = "text",
    attrs?: React.InputHTMLAttributes<HTMLInputElement>
  ) => (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={name}
        className="text-xs text-gray-400 uppercase tracking-wider"
      >
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        defaultValue={defaultValue ?? ""}
        {...attrs}
        className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-solar-500"
      />
      {fieldErrors[name] && (
        <p className="text-red-400 text-xs">{fieldErrors[name]}</p>
      )}
    </div>
  );

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-white">
          {creating ? "Welcome to Helio" : "Setup"}
        </h1>
        {creating && (
          <p className="text-sm text-gray-400">
            No system is configured yet. Enter your array&apos;s details to start
            collecting production data. You can change any of this later.
          </p>
        )}
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        {creating &&
          field("Enphase System ID", "enphase_system_id", null, "text", {
            placeholder: "Found in the Enlighten URL",
          })}
        {field("System Name", "name", data?.name ?? null)}
        {field("Location", "location", data?.location ?? null)}
        <div className="grid grid-cols-2 gap-4">
          {field("Latitude", "latitude", data?.latitude ?? null, "number", {
            min: -90,
            max: 90,
            step: "any",
            placeholder: "-90 to 90",
          })}
          {field("Longitude", "longitude", data?.longitude ?? null, "number", {
            min: -180,
            max: 180,
            step: "any",
            placeholder: "-180 to 180",
          })}
        </div>
        <p className="text-xs text-gray-500">
          Coordinates are required to fetch irradiance. Without them the
          irradiance poll is skipped and Performance Ratio stays unavailable.
        </p>
        {/* step="any" on every decimal field: a number input defaults to step=1,
            which makes the browser reject "7.6" as invalid and block submission.
            Bounds mirror SettingsCreate so the form and the API agree. */}
        {field(
          "System Size (kW)",
          "system_size_kw",
          data?.system_size_kw ?? null,
          "number",
          { min: 0, max: 999, step: "any" }
        )}
        {field("Panel Count", "panel_count", data?.panel_count ?? null, "number")}
        {field(
          "Panel Wattage (W)",
          "panel_wattage_w",
          data?.panel_wattage_w ?? null,
          "number"
        )}
        {field("Install Date", "install_date", data?.install_date ?? null, "date")}
        {field(
          "Tilt Angle (deg)",
          "tilt_angle_deg",
          data?.tilt_angle_deg ?? null,
          "number",
          { min: 0, max: 90, step: "any" }
        )}
        {field(
          "Azimuth (deg)",
          "azimuth_deg",
          data?.azimuth_deg ?? null,
          "number",
          { min: 0, max: 360, step: "any" }
        )}
        {field(
          "Degradation Rate (%/yr)",
          "degradation_rate",
          data?.degradation_rate ?? null,
          "number",
          { min: 0, max: 99, step: "any" }
        )}
        {field(
          "Warranty Threshold (%/yr)",
          "warranty_degradation_rate",
          data?.warranty_degradation_rate ?? null,
          "number",
          { min: 0, max: 99, step: "any", placeholder: "From your module warranty" }
        )}
        <div className="grid grid-cols-2 gap-4">
          {field(
            "Energy Rate (per kWh)",
            "energy_rate_per_kwh",
            data?.energy_rate_per_kwh ?? null,
            "number",
            { min: 0, step: "any" }
          )}
          {field(
            "Currency",
            "energy_rate_currency",
            data?.energy_rate_currency ?? null,
            "text",
            { maxLength: 3, placeholder: "USD" }
          )}
        </div>
        {field(
          "Baseline PR",
          "baseline_pr",
          data?.baseline_pr ?? null,
          "number",
          {
            min: 0,
            max: 1,
            step: "any",
            placeholder: "Blank to measure the first year",
          }
        )}
        <p className="text-xs text-gray-500">
          The warranty threshold flags an annual drop steeper than your modules
          are warranted for. The energy rate prices lost production on the
          Efficiency page. The baseline is the Performance Ratio your array was
          commissioned to reach, between 0 and 1: leave it blank and Helio
          measures it from your own first year instead.
        </p>
        <div className="flex flex-col gap-1">
          <label
            htmlFor="irradiance_source"
            className="text-xs text-gray-400 uppercase tracking-wider"
          >
            Irradiance Source
          </label>
          <select
            id="irradiance_source"
            name="irradiance_source"
            defaultValue={data?.irradiance_source ?? "nasa"}
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
          >
            <option value="nasa">NASA POWER</option>
            <option value="manual">Manual (disabled)</option>
          </select>
        </div>
        {saveError && <p className="text-red-400 text-sm">{saveError}</p>}
        <button
          type="submit"
          disabled={saving}
          className="bg-solar-500 hover:bg-solar-600 disabled:opacity-50 text-white font-medium px-6 py-2 rounded-lg text-sm"
        >
          {saving
            ? creating
              ? "Creating..."
              : "Saving..."
            : creating
              ? "Create System"
              : "Save Settings"}
        </button>
      </form>
      {/* The callback needs a system row to attach tokens to, so connecting
          only makes sense once the system exists. */}
      {!creating && <EnphaseConnection />}
    </div>
  );
}
