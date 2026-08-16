import clsx from "clsx";
import { YtdPoint } from "../api/client";

interface YtdHistoryProps {
  points: YtdPoint[];
  currentYear: number;
}

/**
 * Year-to-date production for every year on record, as a bar per year.
 *
 * Bars are scaled to the best year rather than to a nameplate figure, so the
 * shape of the chart answers "which year was strongest by now" at a glance.
 */
export function YtdHistory({ points, currentYear }: YtdHistoryProps) {
  if (points.length === 0) return null;

  const best = Math.max(...points.map((point) => point.production_kwh));

  return (
    <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5">
      <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">
        Year to date vs prior years
      </p>
      <p className="text-xs text-gray-500 mb-4">
        1 January to today, every year since install
      </p>
      <ul className="space-y-2">
        {points.map((point) => {
          const isCurrent = point.year === currentYear;
          const ahead = point.pct_change !== null && point.pct_change >= 0;
          return (
            <li key={point.year} className="flex items-center gap-3 text-sm">
              <span
                className={clsx(
                  "w-16 font-mono",
                  isCurrent ? "text-white font-semibold" : "text-gray-400"
                )}
              >
                {point.year}
                {point.is_partial && "*"}
              </span>
              <span className="flex-1 h-3 bg-gray-700/60 rounded-sm overflow-hidden">
                <span
                  className={clsx(
                    "block h-full rounded-sm",
                    isCurrent ? "bg-solar-400" : "bg-gray-500"
                  )}
                  style={{
                    width: `${best > 0 ? (point.production_kwh / best) * 100 : 0}%`,
                  }}
                  data-testid={`ytd-bar-${point.year}`}
                />
              </span>
              <span className="w-24 text-right font-mono text-white">
                {point.production_kwh.toFixed(0)} kWh
              </span>
              <span
                className={clsx(
                  "w-20 text-right font-medium",
                  point.pct_change === null
                    ? "text-gray-500"
                    : ahead
                      ? "text-green-400"
                      : "text-red-400"
                )}
              >
                {isCurrent
                  ? "this year"
                  : point.pct_change === null
                    ? "-"
                    : `${ahead ? "+" : ""}${point.pct_change.toFixed(1)}%`}
              </span>
            </li>
          );
        })}
      </ul>
      {points.some((point) => point.is_partial) && (
        <p className="text-xs text-gray-500 mt-4">
          * Partial year: the system was installed part way through it, so the
          total is lower for reasons other than performance.
        </p>
      )}
    </div>
  );
}
