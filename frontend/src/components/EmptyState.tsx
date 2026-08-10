import clsx from "clsx";
import { ReactNode } from "react";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  tone?: "neutral" | "alert";
  children: ReactNode;
  action?: ReactNode;
}

export function EmptyState({
  icon,
  title,
  tone = "neutral",
  children,
  action,
}: EmptyStateProps) {
  return (
    <div className="max-w-xl py-8">
      <span
        className={clsx(
          "inline-flex h-11 w-11 items-center justify-center rounded-xl shadow-lg shadow-black/40",
          tone === "alert"
            ? "bg-red-500/15 text-red-300"
            : "bg-solar-500/15 text-solar-400"
        )}
      >
        {icon}
      </span>
      <h2 className="mt-5 text-xl font-semibold tracking-tight text-white">
        {title}
      </h2>
      <div className="mt-3 space-y-2 text-sm leading-relaxed text-gray-300">
        {children}
      </div>
      {action && (
        <div className="mt-6 flex flex-wrap items-center gap-3">{action}</div>
      )}
    </div>
  );
}
