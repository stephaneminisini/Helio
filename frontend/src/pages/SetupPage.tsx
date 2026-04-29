import { useState } from "react";
import { SystemSettings } from "../api/client";
import { useSettings } from "../hooks/useSettings";

export function SetupPage() {
  const { data, loading, error, save } = useSettings();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  if (loading) return <div className="text-gray-400 p-8">Loading...</div>;
  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;
  if (!data) return null;

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    setSaving(true);
    setSaveError(null);
    try {
      await save({
        name: fd.get("name") as string,
        location: fd.get("location") as string,
        system_size_kw: fd.get("system_size_kw") as string,
        panel_count: fd.get("panel_count")
          ? Number(fd.get("panel_count"))
          : null,
        panel_wattage_w: fd.get("panel_wattage_w")
          ? Number(fd.get("panel_wattage_w"))
          : null,
        install_date: fd.get("install_date") as string,
        tilt_angle_deg: fd.get("tilt_angle_deg") as string,
        azimuth_deg: fd.get("azimuth_deg") as string,
        degradation_rate: fd.get("degradation_rate") as string,
        irradiance_source: fd.get("irradiance_source") as string,
      } as Partial<SystemSettings>);
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
    type = "text"
  ) => (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-gray-400 uppercase tracking-wider">
        {label}
      </label>
      <input
        name={name}
        type={type}
        defaultValue={defaultValue ?? ""}
        className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-solar-500"
      />
    </div>
  );

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-white">Setup</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        {field("System Name", "name", data.name)}
        {field("Location", "location", data.location)}
        {field("System Size (kW)", "system_size_kw", data.system_size_kw, "number")}
        {field("Panel Count", "panel_count", data.panel_count, "number")}
        {field("Panel Wattage (W)", "panel_wattage_w", data.panel_wattage_w, "number")}
        {field("Install Date", "install_date", data.install_date, "date")}
        {field("Tilt Angle (deg)", "tilt_angle_deg", data.tilt_angle_deg, "number")}
        {field("Azimuth (deg)", "azimuth_deg", data.azimuth_deg, "number")}
        {field(
          "Degradation Rate (%/yr)",
          "degradation_rate",
          data.degradation_rate,
          "number"
        )}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-400 uppercase tracking-wider">
            Irradiance Source
          </label>
          <select
            name="irradiance_source"
            defaultValue={data.irradiance_source}
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
          >
            <option value="nrel">NREL</option>
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
          {saving ? "Saving..." : "Save Settings"}
        </button>
      </form>
    </div>
  );
}
