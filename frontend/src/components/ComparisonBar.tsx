import clsx from "clsx";

interface ComparisonBarProps {
  label: string;
  current: number;
  prior: number | null;
  pctChange: number | null;
  unit?: string;
}

export function ComparisonBar({
  label,
  current,
  prior,
  pctChange,
  unit = "kWh",
}: ComparisonBarProps) {
  const positive = pctChange !== null && pctChange >= 0;
  return (
    <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5">
      <p className="text-xs text-gray-400 uppercase tracking-wider mb-3">{label}</p>
      <div className="flex items-end justify-between">
        <div>
          <span className="text-2xl font-semibold text-white">
            {current.toFixed(1)} {unit}
          </span>
          {prior !== null && (
            <span className="ml-2 text-sm text-gray-400">vs {prior.toFixed(1)}</span>
          )}
        </div>
        {pctChange !== null && (
          <span
            className={clsx(
              "text-sm font-medium px-2 py-1 rounded-md",
              positive
                ? "text-green-400 bg-green-400/10"
                : "text-red-400 bg-red-400/10"
            )}
          >
            {positive ? "+" : ""}
            {pctChange.toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  );
}
