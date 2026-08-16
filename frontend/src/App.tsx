import { useState } from "react";
import clsx from "clsx";
import { EfficiencyPage } from "./pages/EfficiencyPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PanelsPage } from "./pages/PanelsPage";
import { SetupPage } from "./pages/SetupPage";

type Tab = "overview" | "efficiency" | "panels" | "setup";

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "efficiency", label: "Efficiency" },
    { id: "panels", label: "Panels" },
    { id: "setup", label: "Setup" },
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-8">
        <span className="text-solar-400 font-bold text-lg tracking-tight">
          Helio Monitor
        </span>
        <nav className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={clsx(
                "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                tab === t.id
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-white"
              )}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="px-6 py-8 max-w-6xl mx-auto">
        {tab === "overview" && <OverviewPage />}
        {tab === "efficiency" && <EfficiencyPage />}
        {tab === "panels" && <PanelsPage />}
        {tab === "setup" && <SetupPage />}
      </main>
    </div>
  );
}
