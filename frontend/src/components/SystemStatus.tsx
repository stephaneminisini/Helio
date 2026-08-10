import clsx from "clsx";
import { ReactNode } from "react";
import { StatusData } from "../api/client";
import { StatusController } from "../hooks/useStatus";
import { Button } from "./Button";
import { AlertIcon, CheckIcon, SpinnerIcon, SunIcon } from "./icons";

type Tone = "alert" | "notice" | "ok";

interface StatusRow {
  key: string;
  tone: Tone;
  icon: ReactNode;
  title: string;
  detail: string;
  action?: { label: string; onClick: () => void; pending?: boolean };
  progress?: { completed: number; total: number };
}

const TONE_STYLES: Record<Tone, string> = {
  alert: "bg-red-500/15 text-red-300",
  notice: "bg-solar-500/15 text-solar-400",
  ok: "bg-emerald-500/15 text-emerald-300",
};

function formatMoment(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function buildRows(
  status: StatusData,
  controller: StatusController,
  onGoToSetup: () => void
): StatusRow[] {
  const rows: StatusRow[] = [];
  const { backfill, last_poll } = status;

  if (backfill.running) {
    const failedNote =
      backfill.failed_days > 0
        ? ` ${backfill.failed_days} day${backfill.failed_days === 1 ? "" : "s"} could not be fetched and will be retried on the next run.`
        : "";
    rows.push({
      key: "backfill-running",
      tone: "notice",
      icon: <SpinnerIcon />,
      title:
        backfill.total_days > 0
          ? `Backfilling day ${backfill.completed_days} of ${backfill.total_days}`
          : "Backfill starting",
      detail:
        `Enphase is rate-limited, so history is walked one day at a time. You can keep using the dashboard.` +
        failedNote,
      progress:
        backfill.total_days > 0
          ? { completed: backfill.completed_days, total: backfill.total_days }
          : undefined,
    });
  }

  if (backfill.error) {
    rows.push({
      key: "backfill-error",
      tone: "alert",
      icon: <AlertIcon />,
      title: "Backfill stopped",
      detail: backfill.error,
      action: backfill.running
        ? undefined
        : {
            label: "Try again",
            onClick: () => void controller.startBackfill(),
            pending: controller.starting,
          },
    });
  }

  if (last_poll && last_poll.status === "error") {
    rows.push({
      key: "poll-error",
      tone: "alert",
      icon: <AlertIcon />,
      title: `Last ${last_poll.poll_type ?? "poll"} failed`,
      detail: `${formatMoment(last_poll.started_at)} - ${last_poll.error_message ?? "no reason recorded"}`,
    });
  }

  if (!status.location_configured) {
    rows.push({
      key: "no-coordinates",
      tone: "alert",
      icon: <AlertIcon />,
      title: "Site coordinates are missing",
      detail:
        "Irradiance is fetched for a point on the globe. Without latitude and longitude, Performance Ratio is measured against sunlight at 0N 0E and means nothing.",
      action: { label: "Add coordinates", onClick: onGoToSetup },
    });
  }

  if (!backfill.running && status.missing_days > 0) {
    rows.push({
      key: "missing-days",
      tone: "notice",
      icon: <SunIcon />,
      title: `${status.missing_days} of ${status.days_expected} days still missing`,
      detail:
        status.first_day && status.last_day
          ? `History currently covers ${status.first_day} to ${status.last_day}. Backfill fills the rest from your install date.`
          : "Backfill walks forward from your install date to yesterday.",
      action: {
        label: "Start backfill",
        onClick: () => void controller.startBackfill(),
        pending: controller.starting,
      },
    });
  }

  if (!status.weather_normalized && status.irradiance_source) {
    rows.push({
      key: "irradiance-source",
      tone: "notice",
      icon: <SunIcon />,
      title: "Performance Ratio is not weather-adjusted",
      detail: `Irradiance comes from ${status.irradiance_source.toUpperCase()}, which returns a 30-year typical year and ignores the date, so a cloudy month reads as underperformance. For real per-day irradiance set IRRADIANCE_SOURCE=nasa in .env and restart the API.`,
    });
  }

  return rows;
}

function healthyRow(status: StatusData): StatusRow {
  const coverage =
    status.first_day && status.last_day
      ? `History covers ${status.first_day} to ${status.last_day} (${status.days_with_data} days).`
      : "No days stored yet.";
  const poll = status.last_poll
    ? `Last ${status.last_poll.poll_type ?? "poll"} succeeded ${formatMoment(status.last_poll.started_at)}.`
    : "The daily poll has not run yet.";
  return {
    key: "healthy",
    tone: "ok",
    icon: <CheckIcon />,
    title: "Ingestion is up to date",
    detail: `${poll} ${coverage}`,
  };
}

interface SystemStatusProps {
  status: StatusData;
  controller: StatusController;
  onGoToSetup: () => void;
  /** "attention" renders nothing when there is nothing to act on. */
  variant?: "attention" | "full";
}

export function SystemStatus({
  status,
  controller,
  onGoToSetup,
  variant = "attention",
}: SystemStatusProps) {
  const rows = buildRows(status, controller, onGoToSetup);
  if (variant === "full" && rows.length === 0) rows.push(healthyRow(status));
  if (rows.length === 0 && !controller.startError) return null;

  return (
    <section
      aria-label="Ingestion status"
      className="divide-y divide-gray-800 overflow-hidden rounded-xl border border-gray-700 bg-gray-800/40"
    >
      {rows.map((row) => (
        <div key={row.key} className="flex gap-3 p-4">
          <span
            className={clsx(
              "mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              TONE_STYLES[row.tone]
            )}
          >
            {row.icon}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-white">{row.title}</p>
            <p className="mt-1 text-sm leading-relaxed text-gray-400">
              {row.detail}
            </p>
            {row.progress && (
              <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-700">
                <div
                  className="h-full rounded-full bg-solar-500 transition-[width] duration-700 ease-expo"
                  style={{
                    width: `${Math.round((row.progress.completed / row.progress.total) * 100)}%`,
                  }}
                />
              </div>
            )}
            {row.action && (
              <Button
                variant="secondary"
                className="mt-3"
                onClick={row.action.onClick}
                disabled={row.action.pending}
              >
                {row.action.pending && <SpinnerIcon className="h-4 w-4" />}
                {row.action.label}
              </Button>
            )}
          </div>
        </div>
      ))}
      {controller.startError && (
        <p className="p-4 text-sm text-red-300">{controller.startError}</p>
      )}
    </section>
  );
}
