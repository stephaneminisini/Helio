import { render, screen } from "@testing-library/react";
import { TooltipProps } from "recharts";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  EfficiencyData,
  MonthlyPRPoint,
  ProjectionSummary,
} from "../api/client";
import { response, stubFetch } from "../test/fetchStub";
import {
  anomalyDot,
  EfficiencyPage,
  PRChartPoint,
  prAxisDomain,
  PRTooltip,
  toChartData,
} from "./EfficiencyPage";

const EFFICIENCY_PATH = "/api/efficiency";

function efficiency(
  overrides: Partial<EfficiencyData["degradation"]> = {},
  pr_history: MonthlyPRPoint[] = [],
  projection: Partial<ProjectionSummary> = {}
): EfficiencyData {
  return {
    pr_history,
    projection: {
      months_of_history: 0,
      annual_rate: null,
      low_confidence: true,
      warranty_breach_year: null,
      years: [],
      ...projection,
    },
    degradation: {
      annual_rates: {},
      lost_kwh: 120,
      lost_dollars: 18,
      warranty_threshold: 0.7,
      exceeds_warranty: false,
      energy_rate_per_kwh: 0.15,
      energy_rate_currency: "USD",
      baseline_pr: 0.82,
      baseline_source: "measured",
      ...overrides,
    },
  };
}

function month(
  overrides: Partial<MonthlyPRPoint> = {}
): MonthlyPRPoint {
  return {
    month: "2024-06-01",
    production_kwh: 880.5,
    performance_ratio: 0.76,
    expected_pr: 0.98,
    is_anomaly: false,
    anomaly_reason: null,
    ...overrides,
  };
}

function point(overrides: Partial<PRChartPoint> = {}): PRChartPoint {
  return {
    month: "2024-06",
    pr: 76,
    expected: 98,
    projected: null,
    isAnomaly: false,
    reason: null,
    ...overrides,
  };
}

/** Recharts hands the tooltip a payload of series entries; only ours matters. */
function payloadFor(chartPoint: PRChartPoint): TooltipProps<
  number,
  string
>["payload"] {
  return [{ payload: chartPoint }] as TooltipProps<
    number,
    string
  >["payload"];
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EfficiencyPage", () => {
  it("shows the configured rate and currency next to the lost-production estimate", async () => {
    stubFetch({ [EFFICIENCY_PATH]: response(200, efficiency()) });

    render(<EfficiencyPage />);

    expect(await screen.findByText("120 kWh")).toBeInTheDocument();
    expect(screen.getByText("18 USD at 0.15/kWh")).toBeInTheDocument();
  });

  it("reports a non-default rate rather than a hardcoded one", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(
        200,
        efficiency({ energy_rate_per_kwh: 0.235, energy_rate_currency: "EUR" })
      ),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("18 EUR at 0.235/kWh")).toBeInTheDocument();
  });

  it("shows the configured warranty threshold", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(200, efficiency({ warranty_threshold: 0.5 })),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("0.5%/yr")).toBeInTheDocument();
  });

  it("states the measured baseline the flags and the losses rest on", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(
        200,
        efficiency({ baseline_pr: 0.815, baseline_source: "measured" })
      ),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("Baseline PR")).toBeInTheDocument();
    expect(screen.getByText("81.5%")).toBeInTheDocument();
    expect(screen.getByText("Measured from the first year")).toBeInTheDocument();
  });

  it("says so when the baseline came from the system's own settings", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(
        200,
        efficiency({ baseline_pr: 0.86, baseline_source: "configured" })
      ),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("86.0%")).toBeInTheDocument();
    expect(screen.getByText("Configured for this system")).toBeInTheDocument();
  });

  it("explains an absent baseline rather than silently flagging nothing", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(
        200,
        efficiency({ baseline_pr: null, baseline_source: "none" })
      ),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText(/No baseline yet/)).toBeInTheDocument();
    expect(screen.queryByText("Baseline PR")).not.toBeInTheDocument();
  });

  it("counts the flagged months without waiting for a hover", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(
        200,
        efficiency({}, [
          month({ month: "2024-05-01" }),
          month({ month: "2024-06-01", is_anomaly: true, anomaly_reason: "a" }),
          month({ month: "2024-07-01", is_anomaly: true, anomaly_reason: "b" }),
        ])
      ),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("Anomalies")).toBeInTheDocument();
    expect(screen.getByText("2 months")).toBeInTheDocument();
  });

  it("counts a lone flagged month in the singular", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(
        200,
        efficiency({}, [month({ is_anomaly: true, anomaly_reason: "a" })])
      ),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("1 month")).toBeInTheDocument();
  });

  it("shows no anomaly card when every month is healthy", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(200, efficiency({}, [month(), month()])),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("120 kWh")).toBeInTheDocument();
    expect(screen.queryByText("Anomalies")).not.toBeInTheDocument();
  });

  it("reports the projected trend and the history behind it", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(
        200,
        efficiency({}, [month()], {
          months_of_history: 36,
          annual_rate: 0.008,
          low_confidence: false,
          years: [{ year: 2025, projected_pr: 0.74 }],
        })
      ),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("Projected Trend")).toBeInTheDocument();
    expect(screen.getByText("0.80%/yr")).toBeInTheDocument();
    expect(screen.getByText("From 36 months of history")).toBeInTheDocument();
  });

  it("warns when the projection rests on less than a year", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(
        200,
        efficiency({}, [month()], {
          months_of_history: 6,
          annual_rate: 0.008,
          low_confidence: true,
          years: [{ year: 2025, projected_pr: 0.74 }],
        })
      ),
    });

    render(<EfficiencyPage />);

    expect(
      await screen.findByText("Low confidence: 6 months of history")
    ).toBeInTheDocument();
  });

  it("calls out the year the projection breaches the warranty", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(
        200,
        efficiency({}, [month()], {
          months_of_history: 24,
          annual_rate: 0.012,
          low_confidence: false,
          warranty_breach_year: 2027,
          years: [{ year: 2027, projected_pr: 0.7 }],
        })
      ),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("Warranty Breach")).toBeInTheDocument();
    expect(screen.getByText("2027")).toBeInTheDocument();
  });

  it("shows no projection card without enough history to project", async () => {
    stubFetch({
      [EFFICIENCY_PATH]: response(200, efficiency({}, [month()])),
    });

    render(<EfficiencyPage />);

    expect(await screen.findByText("120 kWh")).toBeInTheDocument();
    expect(screen.queryByText("Projected Trend")).not.toBeInTheDocument();
    expect(screen.queryByText("Warranty Breach")).not.toBeInTheDocument();
  });
});

describe("toChartData", () => {
  it("carries the anomaly flag and its reason onto the plotted point", () => {
    const [plotted] = toChartData([
      month({ is_anomaly: true, anomaly_reason: "PR 76.0% is 22.0% below" }),
    ]);

    expect(plotted).toEqual({
      month: "2024-06",
      pr: 76,
      expected: 98,
      projected: null,
      isAnomaly: true,
      reason: "PR 76.0% is 22.0% below",
    });
  });

  it("appends the projected years after the measured months", () => {
    const plotted = toChartData(
      [month({ month: "2024-06-01" })],
      [
        { year: 2025, projected_pr: 0.74 },
        { year: 2026, projected_pr: 0.73 },
      ]
    );

    expect(plotted.map((p) => p.month)).toEqual(["2024-06", "2025", "2026"]);
    expect(plotted[1]).toEqual({
      month: "2025",
      pr: null,
      expected: null,
      projected: 74,
      isAnomaly: false,
      reason: null,
    });
  });

  it("bridges the forecast to the last measured month", () => {
    const plotted = toChartData(
      [month({ month: "2024-05-01" }), month({ month: "2024-06-01" })],
      [{ year: 2025, projected_pr: 0.74 }]
    );

    expect(plotted[0].projected).toBeNull();
    expect(plotted[1].projected).toBe(plotted[1].pr);
  });

  it("adds no bridge point when there is nothing to project", () => {
    const plotted = toChartData([month(), month()]);

    expect(plotted.every((p) => p.projected === null)).toBe(true);
  });

  it("leaves a month without a performance ratio unplotted", () => {
    const [plotted] = toChartData([
      month({ performance_ratio: null, expected_pr: null }),
    ]);

    expect(plotted.pr).toBeNull();
    expect(plotted.expected).toBeNull();
  });
});

describe("anomalyDot", () => {
  it("draws a marker on a flagged month", () => {
    const { container } = render(
      <svg>{anomalyDot({ cx: 10, cy: 20, payload: point({ isAnomaly: true }) })}</svg>
    );

    const dot = container.querySelector("circle");
    expect(dot).not.toBeNull();
    expect(dot).toHaveAttribute("cx", "10");
    expect(dot).toHaveAttribute("fill", "#ef4444");
  });

  it("draws nothing on an unflagged month", () => {
    const { container } = render(
      <svg>{anomalyDot({ cx: 10, cy: 20, payload: point() })}</svg>
    );

    expect(container.querySelector("circle")).toBeNull();
  });
});

describe("PRTooltip", () => {
  it("explains how far below expected a flagged month fell", () => {
    render(
      <PRTooltip
        active
        payload={payloadFor(
          point({
            isAnomaly: true,
            reason: "PR 76.0% is 22.0% below expected 98.0%",
          })
        )}
      />
    );

    expect(screen.getByText("2024-06")).toBeInTheDocument();
    expect(screen.getByText("Actual PR 76%")).toBeInTheDocument();
    expect(
      screen.getByText("PR 76.0% is 22.0% below expected 98.0%")
    ).toBeInTheDocument();
  });

  it("says nothing about anomalies on a healthy month", () => {
    render(<PRTooltip active payload={payloadFor(point())} />);

    expect(screen.getByText("Expected PR 98%")).toBeInTheDocument();
    expect(screen.queryByText(/below expected/)).not.toBeInTheDocument();
  });

  it("labels a projected year as projected rather than missing", () => {
    render(
      <PRTooltip
        active
        payload={payloadFor(
          point({
            month: "2025",
            pr: null,
            expected: null,
            projected: 74,
          })
        )}
      />
    );

    expect(screen.getByText("Projected PR 74%")).toBeInTheDocument();
    expect(screen.queryByText(/Actual PR/)).not.toBeInTheDocument();
  });

  it("renders nothing while the chart is not hovered", () => {
    const { container } = render(
      <PRTooltip active={false} payload={payloadFor(point())} />
    );

    expect(container).toBeEmptyDOMElement();
  });
});

describe("prAxisDomain", () => {
  /** Plot a measured series, optionally against an expected one. */
  function points(
    pr: (number | null)[],
    expected: (number | null)[] = []
  ): PRChartPoint[] {
    return pr.map((value, index) => ({
      month: `2020-${String(index + 1).padStart(2, "0")}`,
      pr: value,
      expected: expected[index] ?? null,
      projected: null,
      isAnomaly: false,
      reason: null,
    }));
  }

  it("gives three years of real decline a legible share of the plot", () => {
    // Half a point a year, which is what an ordinary array actually loses. On
    // the old fixed 60-100 axis this was under 4% of the height: a flat line.
    const measured = [83.0, 82.6, 82.2, 81.9, 81.5];

    const [min, max] = prAxisDomain(points(measured));

    const used = (83.0 - 81.5) / (max - min);
    expect(used).toBeGreaterThan(0.25);
  });

  it("keeps the measured and expected series apart on one scale", () => {
    // Both series are framed together, so the gap between them is a real gap
    // rather than an artefact of each being scaled to fill its own chart.
    const [min, max] = prAxisDomain(points([80.0, 79.8], [82.0, 81.9]));

    expect(min).toBeLessThanOrEqual(80.0);
    expect(max).toBeGreaterThanOrEqual(82.0);
    expect((82.0 - 79.8) / (max - min)).toBeGreaterThan(0.25);
  });

  it("does not magnify a flat series into a trend", () => {
    // The floor is the whole reason the domain is not simply [min, max]: a
    // system with nothing happening must not be drawn as though something is.
    expect(prAxisDomain(points([82.0, 82.0, 82.0, 82.0]))).toEqual([80, 84]);
  });

  it("holds the floor when a flat series only wobbles", () => {
    const [min, max] = prAxisDomain(points([82.0, 82.1, 81.9, 82.0]));

    expect(max - min).toBeGreaterThanOrEqual(4);
    expect((82.1 - 81.9) / (max - min)).toBeLessThan(0.1);
  });

  it("pads proportionally once the range is already wide", () => {
    // A wide range needs breathing room, not a fixed floor, or the outermost
    // points would sit on the axis itself.
    const [min, max] = prAxisDomain(points([90.0, 60.0]));

    expect(min).toBeLessThan(60);
    expect(max).toBeGreaterThan(90);
    expect(max - min).toBeLessThan(45);
  });

  it("includes the projection, so the forecast is not drawn off the axis", () => {
    const withProjection: PRChartPoint[] = [
      ...points([82.0, 81.8]),
      {
        month: "2027",
        pr: null,
        expected: null,
        projected: 74.0,
        isAnomaly: false,
        reason: null,
      },
    ];

    const [min] = prAxisDomain(withProjection);

    expect(min).toBeLessThanOrEqual(74.0);
  });

  it("never proposes a negative Performance Ratio", () => {
    const [min] = prAxisDomain(points([1.0, 1.0]));

    expect(min).toBe(0);
  });

  it("falls back to the old fixed axis with nothing plotted", () => {
    expect(prAxisDomain([])).toEqual([60, 100]);
    expect(prAxisDomain(points([null, null]))).toEqual([60, 100]);
  });
});
