import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  TooltipProps,
  XAxis,
  YAxis,
} from "recharts";
import { MonthlyPRPoint, ProjectedYear } from "../api/client";
import { StatCard } from "../components/StatCard";
import { useEfficiency } from "../hooks/useEfficiency";

/** One plotted month. The anomaly flag and its reason travel with the point so
 * the dot renderer and the tooltip can both reach them. `projected` is a
 * separate series from `pr` so measured history is never drawn as a forecast. */
export interface PRChartPoint {
  month: string;
  pr: number | null;
  expected: number | null;
  projected: number | null;
  isAnomaly: boolean;
  reason: string | null;
}

/**
 * Turn the API's PR history into plottable percentages, followed by the
 * projected years.
 *
 * The last measured month also carries a `projected` value so the forecast line
 * starts where the history ends rather than floating away from it; that bridge
 * point is the only place the two series overlap.
 */
export function toChartData(
  history: MonthlyPRPoint[],
  projection: ProjectedYear[] = []
): PRChartPoint[] {
  const measured = history.map((p) => ({
    month: p.month.slice(0, 7),
    pr:
      p.performance_ratio !== null
        ? +(p.performance_ratio * 100).toFixed(1)
        : null,
    expected: p.expected_pr !== null ? +(p.expected_pr * 100).toFixed(1) : null,
    projected: null as number | null,
    isAnomaly: p.is_anomaly,
    reason: p.anomaly_reason,
  }));

  const last = measured[measured.length - 1];
  if (projection.length > 0 && last !== undefined) {
    last.projected = last.pr;
  }

  return [
    ...measured,
    ...projection.map((year) => ({
      month: String(year.year),
      pr: null,
      expected: null,
      projected: +(year.projected_pr * 100).toFixed(1),
      isAnomaly: false,
      reason: null,
    })),
  ];
}

/**
 * Draw a dot only on flagged months, so an anomaly stands out against a line
 * that is otherwise bare. Recharts calls this once per point and requires an
 * SVG element back, hence the empty group for unflagged months.
 */
export function anomalyDot(props: {
  cx?: number;
  cy?: number;
  payload?: PRChartPoint;
}) {
  const { cx, cy, payload } = props;
  if (!payload?.isAnomaly || cx === undefined || cy === undefined) {
    return <g />;
  }
  return (
    <circle cx={cx} cy={cy} r={5} fill="#ef4444" stroke="#fef2f2" strokeWidth={2}>
      <title>{`Anomaly in ${payload.month}`}</title>
    </circle>
  );
}

/** Chart tooltip; adds the anomaly explanation on flagged months. */
export function PRTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as PRChartPoint;
  // A year with no measured PR is a projected one; say so rather than reporting
  // the actual value as missing.
  const isProjected = point.pr === null && point.projected !== null;
  return (
    <div className="bg-gray-800 rounded-lg px-3 py-2 text-xs">
      <p className="text-gray-50 font-medium">{point.month}</p>
      {isProjected ? (
        <p className="text-gray-300">Projected PR {point.projected}%</p>
      ) : (
        <p className="text-solar-400">
          Actual PR {point.pr !== null ? `${point.pr}%` : "not available"}
        </p>
      )}
      {point.expected !== null && (
        <p className="text-gray-400">Expected PR {point.expected}%</p>
      )}
      {point.reason !== null && <p className="text-red-400">{point.reason}</p>}
    </div>
  );
}

export function EfficiencyPage() {
  const { data, loading, error } = useEfficiency();

  if (loading) return <div className="text-gray-400 p-8">Loading...</div>;
  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;
  if (!data) return null;

  const { degradation, pr_history, projection } = data;
  const chartData = toChartData(pr_history, projection.years);
  const anomalies = pr_history.filter((p) => p.is_anomaly).length;
  const projected = projection.years.length > 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Efficiency</h1>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Lost Production"
          value={`${degradation.lost_kwh.toFixed(0)} kWh`}
          // The rate is shown with the figure: the estimate is not
          // interpretable without knowing what it was priced at.
          sub={`${degradation.lost_dollars.toFixed(0)} ${degradation.energy_rate_currency} at ${degradation.energy_rate_per_kwh}/kWh`}
          highlight={degradation.exceeds_warranty}
        />
        <StatCard
          label="Warranty Threshold"
          value={`${degradation.warranty_threshold.toFixed(1)}%/yr`}
        />
        {/* A healthy system has no anomalies, so the card only appears when
            there is something to report. */}
        {anomalies > 0 && (
          <StatCard
            label="Anomalies"
            value={`${anomalies} ${anomalies === 1 ? "month" : "months"}`}
            sub="Below expected PR"
            highlight
          />
        )}
        {projected && projection.annual_rate !== null && (
          <StatCard
            label="Projected Trend"
            value={`${(projection.annual_rate * 100).toFixed(2)}%/yr`}
            // The confidence caveat travels with the figure so a projection off
            // a few months is never read as firmly as one off several years.
            sub={
              projection.low_confidence
                ? `Low confidence: ${projection.months_of_history} months of history`
                : `From ${projection.months_of_history} months of history`
            }
          />
        )}
        {projection.warranty_breach_year !== null && (
          <StatCard
            label="Warranty Breach"
            value={String(projection.warranty_breach_year)}
            sub="Projected below warranty"
            highlight
          />
        )}
        {degradation.exceeds_warranty && (
          <StatCard label="Status" value="Above Threshold" highlight />
        )}
      </div>

      <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5">
        <p className="text-sm text-gray-400 mb-4">
          Performance Ratio history (%)
          {projected && " - the dotted line ahead is projected, not measured"}
        </p>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <XAxis
              dataKey="month"
              tick={{ fill: "#9ca3af", fontSize: 11 }}
            />
            <YAxis
              // 60 is the usual floor, but a projection heading below it has to
              // stay on the chart rather than being clipped away.
              domain={[(dataMin: number) => Math.min(60, Math.floor(dataMin)), 100]}
              tick={{ fill: "#9ca3af", fontSize: 11 }}
            />
            <Tooltip content={<PRTooltip />} />
            <Line
              type="monotone"
              dataKey="pr"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={anomalyDot}
              name="Actual PR %"
            />
            {/* Same amber as the measured line, but dotted and dot-less: the
                projection continues the same quantity without pretending any of
                it was recorded. */}
            <Line
              type="monotone"
              dataKey="projected"
              stroke="#fbbf24"
              strokeWidth={2}
              strokeDasharray="2 4"
              dot={false}
              name="Projected PR %"
            />
            <Line
              type="monotone"
              dataKey="expected"
              stroke="#6b7280"
              strokeWidth={1}
              strokeDasharray="4 4"
              dot={false}
              name="Expected PR %"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
