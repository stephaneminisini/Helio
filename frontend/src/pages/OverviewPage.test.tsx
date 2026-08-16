import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ComparisonPair, OverviewData } from "../api/client";
import { response, stubFetch } from "../test/fetchStub";
import { OverviewPage } from "./OverviewPage";

const OVERVIEW_PATH = "/api/overview";

function pair(
  current: number,
  prior: number | null,
  pctChange: number | null
): ComparisonPair {
  return { current_kwh: current, prior_kwh: prior, pct_change: pctChange };
}

function overview(overrides: Partial<OverviewData> = {}): OverviewData {
  return {
    today: "2025-07-12",
    today_kwh: 30,
    current_power_w: null,
    day_comparison: pair(30, 20, 50),
    day_vs_last_month: pair(30, 24, 25),
    month_comparison: pair(400, 320, 25),
    month_vs_last_year: pair(400, 500, -20),
    ytd_history: [
      { year: 2023, production_kwh: 3600, pct_change: 11.1, is_partial: true },
      { year: 2024, production_kwh: 3800, pct_change: 5.3, is_partial: false },
      { year: 2025, production_kwh: 4000, pct_change: null, is_partial: false },
    ],
    best_day_kwh: 45,
    best_day_date: "2025-06-21",
    all_time_kwh: 24000,
    ...overrides,
  };
}

/** The card for one comparison, found by its label. */
function card(label: string): HTMLElement {
  const heading = screen.getByText(label);
  const container = heading.parentElement;
  if (container === null) throw new Error(`No card around "${label}"`);
  return container;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("OverviewPage", () => {
  it("shows the four day and month comparisons with their deltas", async () => {
    stubFetch({ [OVERVIEW_PATH]: response(200, overview()) });

    render(<OverviewPage />);

    expect(
      await screen.findByText("Today vs same day last year")
    ).toBeInTheDocument();
    const cases: [string, string, string][] = [
      ["Today vs same day last year", "vs 20.0", "+50.0%"],
      ["Today vs same day last month", "vs 24.0", "+25.0%"],
      ["This month vs last month", "vs 320.0", "+25.0%"],
      ["This month vs same month last year", "vs 500.0", "-20.0%"],
    ];
    for (const [label, prior, delta] of cases) {
      const bar = card(label);
      expect(within(bar).getByText(prior)).toBeInTheDocument();
      expect(within(bar).getByText(delta)).toBeInTheDocument();
    }
  });

  it("renders a dash rather than a percentage when a prior period has no data", async () => {
    stubFetch({
      [OVERVIEW_PATH]: response(
        200,
        overview({ day_vs_last_month: pair(30, null, null) })
      ),
    });

    render(<OverviewPage />);

    await screen.findByText("Today vs same day last month");
    const bar = card("Today vs same day last month");
    expect(within(bar).getByText("vs -")).toBeInTheDocument();
    expect(within(bar).getByText("-")).toBeInTheDocument();
    expect(within(bar).queryByText("0.0%")).not.toBeInTheDocument();
  });

  it("shows a year-to-date row for every year the API returned", async () => {
    stubFetch({ [OVERVIEW_PATH]: response(200, overview()) });

    render(<OverviewPage />);

    expect(
      await screen.findByText("Year to date vs prior years")
    ).toBeInTheDocument();
    const years = screen.getAllByRole("listitem");
    expect(years).toHaveLength(3);
    // today is 2025-07-12, so 2025 is the baseline year.
    expect(within(years[2]).getByText("this year")).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    stubFetch({ [OVERVIEW_PATH]: response(500, { detail: "boom" }) });

    render(<OverviewPage />);

    expect(await screen.findByText(/^Error: API error 500/)).toBeInTheDocument();
  });
});
