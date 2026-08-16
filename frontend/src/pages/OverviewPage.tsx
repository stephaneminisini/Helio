import { ComparisonBar } from "../components/ComparisonBar";
import { StatCard } from "../components/StatCard";
import { YtdHistory } from "../components/YtdHistory";
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

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ComparisonBar
          label="Today vs same day last year"
          current={data.day_comparison.current_kwh}
          prior={data.day_comparison.prior_kwh}
          pctChange={data.day_comparison.pct_change}
        />
        <ComparisonBar
          label="Today vs same day last month"
          current={data.day_vs_last_month.current_kwh}
          prior={data.day_vs_last_month.prior_kwh}
          pctChange={data.day_vs_last_month.pct_change}
        />
        <ComparisonBar
          label="This month vs last month"
          current={data.month_comparison.current_kwh}
          prior={data.month_comparison.prior_kwh}
          pctChange={data.month_comparison.pct_change}
        />
        <ComparisonBar
          label="This month vs same month last year"
          current={data.month_vs_last_year.current_kwh}
          prior={data.month_vs_last_year.prior_kwh}
          pctChange={data.month_vs_last_year.pct_change}
        />
      </div>

      <YtdHistory
        points={data.ytd_history}
        currentYear={Number(data.today.slice(0, 4))}
      />

      <p className="text-xs text-gray-500">
        Month and year comparisons stop at the same day of the prior period, so a
        partial period is never measured against a whole one.
      </p>
    </div>
  );
}
