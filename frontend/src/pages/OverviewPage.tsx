import { Button } from "../components/Button";
import { ComparisonBar } from "../components/ComparisonBar";
import { EmptyState } from "../components/EmptyState";
import { LoadingCards } from "../components/LoadingCards";
import { StatCard } from "../components/StatCard";
import { SystemStatus } from "../components/SystemStatus";
import {
  AlertIcon,
  ArrowRightIcon,
  PlugIcon,
  SpinnerIcon,
  SunIcon,
} from "../components/icons";
import { StatusController } from "../hooks/useStatus";
import { useOverview } from "../hooks/useOverview";

interface OverviewPageProps {
  status: StatusController;
  onGoToSetup: () => void;
}

export function OverviewPage({ status, onGoToSetup }: OverviewPageProps) {
  const { data, loading, error } = useOverview();
  const system = status.data;

  if (system && !system.configured) {
    return (
      <EmptyState
        icon={<PlugIcon />}
        title="Connect your Enphase system"
        action={
          <Button onClick={onGoToSetup}>
            Set up your system
            <ArrowRightIcon className="h-4 w-4" />
          </Button>
        }
      >
        <p>
          Helio needs your Enphase System ID, your install date, and where the
          array actually is before it can pull anything. That is the whole of
          setup and it takes about a minute.
        </p>
        <p>
          After that, this page answers the one question Enlighten will not: how
          today compares to the same day last year.
        </p>
      </EmptyState>
    );
  }

  if (loading || status.loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-white">Overview</h1>
        <LoadingCards count={4} label="Loading production summary" />
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        icon={<AlertIcon />}
        title="Could not load production data"
        tone="alert"
        action={
          <Button variant="secondary" onClick={() => window.location.reload()}>
            Reload
          </Button>
        }
      >
        <p>{error}</p>
      </EmptyState>
    );
  }

  if (!data) return null;

  const hasHistory = (system?.days_with_data ?? 0) > 0;

  if (system && !hasHistory) {
    const running = system.backfill.running;
    return (
      <div className="space-y-6">
        <EmptyState
          icon={running ? <SpinnerIcon /> : <SunIcon />}
          title={running ? "Filling in your history" : "No production data yet"}
          action={
            running ? undefined : (
              <Button
                onClick={() => void status.startBackfill()}
                disabled={status.starting}
              >
                {status.starting && <SpinnerIcon className="h-4 w-4" />}
                Backfill from {system.install_date}
              </Button>
            )
          }
        >
          <p>
            Nothing has been stored yet. Backfill walks day by day from your
            install date to yesterday, pausing between days to stay inside
            Enphase rate limits, so a multi-year system takes a few minutes.
          </p>
          <p>
            Once the first days land, today appears here next to the same day
            last year, this month next to last month, and the year to date next
            to the year before.
          </p>
        </EmptyState>
        <SystemStatus
          status={system}
          controller={status}
          onGoToSetup={onGoToSetup}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Overview</h1>

      {system && (
        <SystemStatus
          status={system}
          controller={status}
          onGoToSetup={onGoToSetup}
        />
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Today"
          value={`${data.today_kwh.toFixed(1)} kWh`}
          sub={`${data.today} - partial until tomorrow's poll`}
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
          pendingNote="Nothing stored for the same day last year yet, so there is no comparison to draw."
        />
        <ComparisonBar
          label="This month vs last month"
          current={data.month_comparison.current_kwh}
          prior={data.month_comparison.prior_kwh}
          pctChange={data.month_comparison.pct_change}
          pendingNote="Nothing stored for last month yet."
        />
        <ComparisonBar
          label="Year to date vs prior year"
          current={data.ytd_comparison.current_kwh}
          prior={data.ytd_comparison.prior_kwh}
          pctChange={data.ytd_comparison.pct_change}
          pendingNote="Nothing stored for the year before this one yet."
        />
      </div>
    </div>
  );
}
