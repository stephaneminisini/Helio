import clsx from "clsx";
import { PanelPoint } from "../api/client";
import { StatCard } from "../components/StatCard";
import { usePanels } from "../hooks/usePanels";

// Buckets are relative to the fleet average rather than to a nameplate rating:
// every panel on the roof saw the same weather, so 1.0 is what the rest of them
// managed under the same conditions.
const BUCKETS = [
  { min: 0.97, color: "bg-lime-400", label: "At fleet average" },
  { min: 0.94, color: "bg-yellow-400", label: "3-6% below" },
  { min: 0.88, color: "bg-orange-400", label: "6-12% below" },
  { min: Number.NEGATIVE_INFINITY, color: "bg-red-400", label: "Over 12% below" },
];

const LAST_BUCKET = BUCKETS[BUCKETS.length - 1];

function panelColor(normalized: number): string {
  return (BUCKETS.find((bucket) => normalized >= bucket.min) ?? LAST_BUCKET).color;
}

/** Describe a panel's standing in words, for the cell's tooltip. */
export function panelTooltip(panel: PanelPoint): string {
  const deltaPct = (panel.normalized_efficiency - 1) * 100;
  const magnitude = Math.abs(deltaPct).toFixed(1);
  const standing =
    Math.abs(deltaPct) < 0.05
      ? "level with the fleet average"
      : `${magnitude}% ${deltaPct < 0 ? "below" : "above"} the fleet average`;
  const sigma =
    panel.deviation_sigma !== null
      ? ` (${panel.deviation_sigma.toFixed(2)} sigma)`
      : "";
  return `${panel.panel_serial}: ${standing}${sigma}`;
}

/** Serials are 12 digits, so only the tail fits a cell; the tooltip has all of it. */
function shortSerial(serial: string): string {
  return serial.length > 4 ? serial.slice(-4) : serial;
}

export function PanelsPage() {
  const { data, loading, error } = usePanels();

  if (loading) return <div className="text-gray-400 p-8">Loading...</div>;
  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;
  if (!data) return null;

  if (!data.data_available) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-white">Panels</h1>
        <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-6 space-y-2">
          <p className="text-white font-medium">
            Per-panel data is not available yet
          </p>
          <p className="text-sm text-gray-400">
            {data.unavailable_reason ??
              "No per-panel readings have been stored for this system."}
          </p>
        </div>
      </div>
    );
  }

  const { panels } = data;
  const underperforming = panels.filter((panel) => panel.is_underperforming);
  const averageKwh = data.fleet_average_wh / 1000;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Panels</h1>
        <p className="text-sm text-gray-400">
          {data.window_start} to {data.window_end}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <StatCard label="Panels Reporting" value={`${panels.length}`} />
        <StatCard
          label="Fleet Average"
          value={`${averageKwh.toFixed(1)} kWh`}
          sub="per panel over the window"
        />
        <StatCard
          label="Underperforming"
          value={`${underperforming.length}`}
          sub="more than 2 sigma below average"
          highlight={underperforming.length > 0}
        />
      </div>

      <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5">
        <p className="text-sm text-gray-400 mb-4">
          Panel-level efficiency heatmap
        </p>
        <div
          className="grid grid-cols-4 gap-1.5 sm:grid-cols-6 md:grid-cols-8"
          role="list"
          aria-label="Panel efficiency heatmap"
        >
          {panels.map((panel) => (
            <div
              key={panel.panel_serial}
              role="listitem"
              title={panelTooltip(panel)}
              className={clsx(
                "aspect-[1.6/1] rounded-md flex flex-col items-center justify-center",
                panelColor(panel.normalized_efficiency),
                panel.is_underperforming &&
                  "ring-2 ring-offset-2 ring-offset-gray-900 ring-red-500"
              )}
            >
              <span className="text-[9px] font-mono font-bold text-black/70">
                {shortSerial(panel.panel_serial)}
                {panel.is_underperforming && " !"}
              </span>
              <span className="text-[11px] font-mono font-bold text-black/80">
                {(panel.normalized_efficiency * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-4 mt-4">
          {BUCKETS.map((bucket) => (
            <div
              key={bucket.label}
              className="flex items-center gap-1.5 text-[11px] text-gray-400"
            >
              <span className={clsx("w-3 h-3 rounded-sm", bucket.color)} />
              {bucket.label}
            </div>
          ))}
        </div>
      </div>

      {underperforming.length > 0 && (
        <div className="bg-solar-500/20 border border-solar-500/40 rounded-xl p-4 text-sm text-solar-50">
          {underperforming.map((panel) => (
            <p key={panel.panel_serial}>{panelTooltip(panel)}</p>
          ))}
          <p className="text-gray-300 mt-2">
            Check these panels for shading, soiling or a microinverter fault.
          </p>
        </div>
      )}
    </div>
  );
}
