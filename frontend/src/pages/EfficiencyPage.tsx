import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { LoadingCards } from "../components/LoadingCards";
import { StatCard } from "../components/StatCard";
import { SystemStatus } from "../components/SystemStatus";
import {
  AlertIcon,
  ArrowRightIcon,
  PlugIcon,
  SpinnerIcon,
  TrendIcon,
} from "../components/icons";
import { StatusController } from "../hooks/useStatus";
import { useEfficiency } from "../hooks/useEfficiency";

interface EfficiencyPageProps {
  status: StatusController;
  onGoToSetup: () => void;
}

export function EfficiencyPage({ status, onGoToSetup }: EfficiencyPageProps) {
  const { data, loading, error } = useEfficiency();
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
          Degradation is measured against your own history, so Helio needs the
          install date and the array location before it can say anything about
          efficiency.
        </p>
      </EmptyState>
    );
  }

  if (loading || status.loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-white">Efficiency</h1>
        <LoadingCards count={3} label="Loading efficiency trend" />
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        icon={<AlertIcon />}
        title="Could not load the efficiency trend"
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

  const { degradation, pr_history } = data;
  const rated = pr_history.filter((p) => p.performance_ratio !== null);

  if (pr_history.length === 0) {
    const running = system?.backfill.running ?? false;
    return (
      <div className="space-y-6">
        <EmptyState
          icon={running ? <SpinnerIcon /> : <TrendIcon />}
          title="Performance Ratio needs a full month"
          action={
            !running && system && system.missing_days > 0 ? (
              <Button
                onClick={() => void status.startBackfill()}
                disabled={status.starting}
              >
                {status.starting && <SpinnerIcon className="h-4 w-4" />}
                Backfill history
              </Button>
            ) : undefined
          }
        >
          <p>
            The efficiency trend is built from monthly rollups, so it appears
            once a full calendar month of production and irradiance is stored.
          </p>
          <p>
            Backfilling from your install date creates every past month at once,
            which is the fastest way to get a real degradation reading rather
            than waiting a month for one.
          </p>
        </EmptyState>
        {system && (
          <SystemStatus
            status={system}
            controller={status}
            onGoToSetup={onGoToSetup}
          />
        )}
      </div>
    );
  }

  if (rated.length === 0) {
    return (
      <div className="space-y-6">
        <EmptyState
          icon={<AlertIcon />}
          title="No Performance Ratio could be computed"
          tone="alert"
        >
          <p>
            {pr_history.length} monthly rollup
            {pr_history.length === 1 ? "" : "s"} exist, but none has irradiance
            attached. Performance Ratio divides your production by what the
            sunlight that month should have produced, so without irradiance
            there is no ratio to show.
          </p>
          <p>
            Check that the irradiance source is reachable and that the site
            coordinates are right, then backfill again.
          </p>
        </EmptyState>
        {system && (
          <SystemStatus
            status={system}
            controller={status}
            onGoToSetup={onGoToSetup}
            variant="full"
          />
        )}
      </div>
    );
  }

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

      {system && (
        <SystemStatus
          status={system}
          controller={status}
          onGoToSetup={onGoToSetup}
        />
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Lost Production"
          value={`${degradation.lost_kwh.toFixed(0)} kWh`}
          sub={`$${degradation.lost_dollars.toFixed(0)} estimated`}
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

      <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-5">
        <p className="mb-4 text-sm text-gray-400">
          Performance Ratio history (%) - {rated.length} of {pr_history.length}{" "}
          months have irradiance
        </p>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <XAxis dataKey="month" tick={{ fill: "#9ca3af", fontSize: 11 }} />
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
