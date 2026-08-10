import clsx from "clsx";

interface ComparisonBarProps {
  label: string;
  current: number;
  prior: number | null;
  pctChange: number | null;
  /** Shown when there is no prior period to compare against. */
  pendingNote?: string;
  unit?: string;
}

export function ComparisonBar({
  label,
  current,
  prior,
  pctChange,
  pendingNote,
  unit = "kWh",
}: ComparisonBarProps) {
  const positive = pctChange !== null && pctChange >= 0;
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-5">
      <p className="mb-3 text-xs uppercase tracking-wider text-gray-400">
        {label}
      </p>
      <div className="flex items-end justify-between gap-3">
        <div>
          <span className="text-2xl font-semibold text-white">
            {current.toFixed(1)} {unit}
          </span>
          {prior !== null && (
            <span className="ml-2 text-sm text-gray-400">
              vs {prior.toFixed(1)}
            </span>
          )}
        </div>
        <span
          className={clsx(
            "shrink-0 rounded-md px-2 py-1 text-sm font-medium",
            pctChange === null
              ? "bg-gray-700/60 text-gray-300"
              : positive
                ? "bg-green-400/10 text-green-400"
                : "bg-red-400/10 text-red-400"
          )}
        >
          {pctChange === null ? "no baseline" : null}
          {pctChange !== null && `${positive ? "+" : ""}${pctChange.toFixed(1)}%`}
        </span>
      </div>
      {prior === null && pendingNote && (
        <p className="mt-3 text-xs leading-relaxed text-gray-400">
          {pendingNote}
        </p>
      )}
    </div>
  );
}
