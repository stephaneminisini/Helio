import { ComparisonBar } from "../components/ComparisonBar";
import { StatCard } from "../components/StatCard";
import { useOverview } from "../hooks/useOverview";

export function OverviewPage() {
  const { data, loading, error } = useOverview();

  if (loading) return <div className="text-gray-400 p-8">Loading...</div>;
  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Overview</h1>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Today"
          value={`${data.today_kwh.toFixed(1)} kWh`}
          sub={data.today}
          highlight
        />
        <StatCard
          label="All Time"
          value={`${(data.all_time_kwh / 1000).toFixed(1)} MWh`}
        />
        {data.best_day_kwh !== null && (
          <StatCard
            label="Best Day"
            value={`${data.best_day_kwh.toFixed(1)} kWh`}
            sub={data.best_day_date ?? undefined}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ComparisonBar
          label="Today vs same day last year"
          current={data.day_comparison.current_kwh}
          prior={data.day_comparison.prior_kwh}
          pctChange={data.day_comparison.pct_change}
        />
        <ComparisonBar
          label="This month vs last month"
          current={data.month_comparison.current_kwh}
          prior={data.month_comparison.prior_kwh}
          pctChange={data.month_comparison.pct_change}
        />
        <ComparisonBar
          label="Year to date vs prior year"
          current={data.ytd_comparison.current_kwh}
          prior={data.ytd_comparison.prior_kwh}
          pctChange={data.ytd_comparison.pct_change}
        />
      </div>
    </div>
  );
}
