import { OverviewData } from "../api/client";
import { ComparisonBar } from "../components/ComparisonBar";
import { StatCard } from "../components/StatCard";
import { YtdHistory } from "../components/YtdHistory";
import { useOverview } from "../hooks/useOverview";

/**
 * Caption for the live power card.
 *
 * A reading is only meaningful with the time it was taken: an envoy reports in
 * batches, so a figure on its own cannot be told apart from a stale one. A
 * stored reading says so outright, because it is the average over the last
 * recorded interval rather than what the array is doing now.
 */
function livePowerSub(
  watts: number | null,
  reportedAt: string | null,
  source: OverviewData["current_power_source"]
): string {
  if (watts === null) return "Enphase did not report a reading";
  if (reportedAt === null) return "Reported without a timestamp";
  const at = new Date(reportedAt).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  return source === "stored"
    ? `Last recorded at ${at}, Enphase unreachable`
    : `Measured at ${at}`;
}

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
          label="Current Power"
          value={
            data.current_power_w !== null
              ? `${data.current_power_w.toFixed(0)} W`
              : "Unavailable"
          }
          sub={livePowerSub(
            data.current_power_w,
            data.current_power_at,
            data.current_power_source
          )}
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
          label="Today so far vs same day last year"
          current={data.day_comparison.current_kwh}
          prior={data.day_comparison.prior_kwh}
          pctChange={data.day_comparison.pct_change}
        />
        <ComparisonBar
          label="Today so far vs same day last month"
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
        Every comparison stops at the same point in the prior period, so a
        partial period is never measured against a whole one. Day comparisons cut
        the prior day at the current time; month and year comparisons stop at the
        same day of the prior period.
      </p>
    </div>
  );
}
