import { render, screen } from "@testing-library/react";
import { TooltipProps } from "recharts";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EfficiencyData, MonthlyPRPoint } from "../api/client";
import { response, stubFetch } from "../test/fetchStub";
import {
  anomalyDot,
  EfficiencyPage,
  PRChartPoint,
  PRTooltip,
  toChartData,
} from "./EfficiencyPage";

const EFFICIENCY_PATH = "/api/efficiency";

function efficiency(
  overrides: Partial<EfficiencyData["degradation"]> = {},
  pr_history: MonthlyPRPoint[] = []
): EfficiencyData {
  return {
    pr_history,
    degradation: {
      annual_rates: {},
      lost_kwh: 120,
      lost_dollars: 18,
      warranty_threshold: 0.7,
      exceeds_warranty: false,
      energy_rate_per_kwh: 0.15,
      energy_rate_currency: "USD",
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
      isAnomaly: true,
      reason: "PR 76.0% is 22.0% below",
    });
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

  it("renders nothing while the chart is not hovered", () => {
    const { container } = render(
      <PRTooltip active={false} payload={payloadFor(point())} />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
