import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { YtdPoint } from "../api/client";
import { YtdHistory } from "./YtdHistory";

function point(overrides: Partial<YtdPoint> = {}): YtdPoint {
  return {
    year: 2024,
    production_kwh: 3800,
    pct_change: 5.3,
    is_partial: false,
    ...overrides,
  };
}

const THREE_YEARS = [
  point({ year: 2023, production_kwh: 3600, pct_change: 11.1, is_partial: true }),
  point({ year: 2024, production_kwh: 3800, pct_change: 5.3 }),
  point({ year: 2025, production_kwh: 4000, pct_change: null }),
];

describe("YtdHistory", () => {
  it("lists every year with its total and delta against the current year", () => {
    render(<YtdHistory points={THREE_YEARS} currentYear={2025} />);

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("3600 kWh")).toBeInTheDocument();
    expect(within(rows[0]).getByText("+11.1%")).toBeInTheDocument();
    expect(within(rows[1]).getByText("3800 kWh")).toBeInTheDocument();
    expect(within(rows[1]).getByText("+5.3%")).toBeInTheDocument();
    // The current year is the baseline, so it has no delta against itself.
    expect(within(rows[2]).getByText("4000 kWh")).toBeInTheDocument();
    expect(within(rows[2]).getByText("this year")).toBeInTheDocument();
  });

  it("marks a partial install year and explains the marker", () => {
    render(<YtdHistory points={THREE_YEARS} currentYear={2025} />);

    expect(screen.getByText("2023*")).toBeInTheDocument();
    expect(screen.getByText("2024")).toBeInTheDocument();
    expect(screen.getByText(/Partial year/)).toBeInTheDocument();
  });

  it("omits the partial-year footnote when every year is whole", () => {
    render(
      <YtdHistory
        points={[point({ year: 2024 }), point({ year: 2025, pct_change: null })]}
        currentYear={2025}
      />
    );

    expect(screen.queryByText(/Partial year/)).not.toBeInTheDocument();
  });

  it("scales the bars against the strongest year", () => {
    render(<YtdHistory points={THREE_YEARS} currentYear={2025} />);

    expect(screen.getByTestId("ytd-bar-2023").style.width).toBe("90%");
    expect(screen.getByTestId("ytd-bar-2024").style.width).toBe("95%");
    expect(screen.getByTestId("ytd-bar-2025").style.width).toBe("100%");
  });

  it("shows a dash when a year has no comparable total", () => {
    render(
      <YtdHistory
        points={[
          point({ year: 2024, production_kwh: 0, pct_change: null }),
          point({ year: 2025, pct_change: null }),
        ]}
        currentYear={2025}
      />
    );

    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("renders nothing when there is no history", () => {
    const { container } = render(<YtdHistory points={[]} currentYear={2025} />);

    expect(container).toBeEmptyDOMElement();
  });
});
