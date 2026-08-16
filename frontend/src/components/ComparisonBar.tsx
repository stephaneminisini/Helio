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
          <span className="ml-2 text-sm text-gray-400">
            vs {prior !== null ? prior.toFixed(1) : "-"}
          </span>
        </div>
        {/* A period with nothing stored gets a dash: no reading at all is not
            the same as a reading of zero percent. */}
        <span
          className={clsx(
            "text-sm font-medium px-2 py-1 rounded-md",
            pctChange === null
              ? "text-gray-400 bg-gray-400/10"
              : positive
                ? "text-green-400 bg-green-400/10"
                : "text-red-400 bg-red-400/10"
          )}
        >
          {pctChange === null
            ? "-"
            : `${positive ? "+" : ""}${pctChange.toFixed(1)}%`}
        </span>
      </div>
    </div>
  );
}
