import clsx from "clsx";
import { useCallback, useEffect, useState } from "react";
import { EfficiencyPage } from "./pages/EfficiencyPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SetupPage } from "./pages/SetupPage";
import { useStatus } from "./hooks/useStatus";

type Tab = "overview" | "efficiency" | "setup";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "efficiency", label: "Efficiency" },
  { id: "setup", label: "Setup" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [steered, setSteered] = useState(false);
  const status = useStatus();
  const goToSetup = useCallback(() => setTab("setup"), []);

  // Land a first-run visitor on Setup once, then leave navigation alone.
  useEffect(() => {
    if (steered || status.loading || !status.data) return;
    setSteered(true);
    if (!status.data.configured) setTab("setup");
  }, [steered, status.loading, status.data]);

  const setupNeedsAttention =
    status.data !== null &&
    (!status.data.configured || !status.data.location_configured);

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="flex flex-col items-start gap-3 border-b border-gray-800 px-6 py-4 sm:flex-row sm:items-center sm:gap-8">
        <span className="text-lg font-bold tracking-tight text-solar-400">
          Helio Monitor
        </span>
        <nav aria-label="Sections" className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              aria-current={tab === t.id ? "page" : undefined}
              className={clsx(
                "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-solar-400",
                "focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950",
                tab === t.id
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-white"
              )}
            >
              {t.label}
              {t.id === "setup" && setupNeedsAttention && (
                <span
                  aria-label="needs attention"
                  className="h-1.5 w-1.5 rounded-full bg-solar-400"
                />
              )}
            </button>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        {tab === "overview" && (
          <OverviewPage status={status} onGoToSetup={goToSetup} />
        )}
        {tab === "efficiency" && (
          <EfficiencyPage status={status} onGoToSetup={goToSetup} />
        )}
        {tab === "setup" && <SetupPage status={status} />}
      </main>
    </div>
  );
}
