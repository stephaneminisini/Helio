import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { StatCard } from "../components/StatCard";
import { useEfficiency } from "../hooks/useEfficiency";

export function EfficiencyPage() {
  const { data, loading, error } = useEfficiency();

  if (loading) return <div className="text-gray-400 p-8">Loading...</div>;
  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;
  if (!data) return null;

  const { degradation, pr_history } = data;
  const chartData = pr_history.map((p) => ({
    month: p.month.slice(0, 7),
    pr:
      p.performance_ratio !== null
        ? +(p.performance_ratio * 100).toFixed(1)
        : null,
    expected:
      p.expected_pr !== null ? +(p.expected_pr * 100).toFixed(1) : null,
  }));

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
        {degradation.exceeds_warranty && (
          <StatCard label="Status" value="Above Threshold" highlight />
        )}
      </div>

      <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5">
        <p className="text-sm text-gray-400 mb-4">Performance Ratio history (%)</p>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <XAxis
              dataKey="month"
              tick={{ fill: "#9ca3af", fontSize: 11 }}
            />
            <YAxis
              domain={[60, 100]}
              tick={{ fill: "#9ca3af", fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#1f2937", border: "none" }}
              labelStyle={{ color: "#f9fafb" }}
            />
            <Line
              type="monotone"
              dataKey="pr"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              name="Actual PR %"
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
