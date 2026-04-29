import clsx from "clsx";

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}

export function StatCard({ label, value, sub, highlight }: StatCardProps) {
  return (
    <div
      className={clsx(
        "rounded-xl p-5 flex flex-col gap-1",
        highlight
          ? "bg-solar-500/20 border border-solar-500/40"
          : "bg-gray-800/60 border border-gray-700"
      )}
    >
      <p className="text-xs text-gray-400 uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-semibold text-white">{value}</p>
      {sub && <p className="text-sm text-gray-400">{sub}</p>}
    </div>
  );
}
