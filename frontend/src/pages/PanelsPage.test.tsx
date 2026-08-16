import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PanelPoint, PanelsData } from "../api/client";
import { response, stubFetch } from "../test/fetchStub";
import { PanelsPage } from "./PanelsPage";

const PANELS_PATH = "/api/panels";

function panel(overrides: Partial<PanelPoint> = {}): PanelPoint {
  return {
    panel_serial: "482218012345",
    energy_wh: 30000,
    normalized_efficiency: 1.0,
    deviation_sigma: 0.1,
    is_underperforming: false,
    ...overrides,
  };
}

function panels(overrides: Partial<PanelsData> = {}): PanelsData {
  return {
    panels: [panel()],
    fleet_average_wh: 30000,
    fleet_stdev_wh: 1200,
    window_start: "2024-04-01",
    window_end: "2024-04-30",
    data_available: true,
    unavailable_reason: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PanelsPage", () => {
  it("renders one cell per panel", async () => {
    stubFetch({
      [PANELS_PATH]: response(
        200,
        panels({
          panels: [
            panel({ panel_serial: "482218012345" }),
            panel({ panel_serial: "482218012346" }),
            panel({ panel_serial: "482218012347" }),
          ],
        })
      ),
    });

    render(<PanelsPage />);

    expect(await screen.findByText("3")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("colours a cell by how it compares to the fleet average", async () => {
    stubFetch({
      [PANELS_PATH]: response(
        200,
        panels({
          panels: [
            panel({ panel_serial: "482218012345", normalized_efficiency: 1.02 }),
            panel({ panel_serial: "482218012346", normalized_efficiency: 0.8 }),
          ],
        })
      ),
    });

    render(<PanelsPage />);

    const cells = await screen.findAllByRole("listitem");
    expect(cells[0].className).toContain("bg-lime-400");
    expect(cells[1].className).toContain("bg-red-400");
  });

  it("marks an underperforming panel and says how far below average it sits", async () => {
    stubFetch({
      [PANELS_PATH]: response(
        200,
        panels({
          panels: [
            panel({ panel_serial: "482218012345" }),
            panel({
              panel_serial: "482218012399",
              normalized_efficiency: 0.444,
              deviation_sigma: -2.236,
              is_underperforming: true,
            }),
          ],
        })
      ),
    });

    render(<PanelsPage />);

    const flagged = await screen.findByTitle(
      "482218012399: 55.6% below the fleet average (-2.24 sigma)"
    );
    // The colour alone is not enough: the cell carries a ring and a marker.
    expect(flagged.className).toContain("ring-red-500");
    expect(flagged).toHaveTextContent("2399 !");
    const healthy = screen.getByTitle(
      "482218012345: level with the fleet average (0.10 sigma)"
    );
    expect(healthy.className).not.toContain("ring-red-500");
  });

  it("names the underperforming panels and what to check", async () => {
    stubFetch({
      [PANELS_PATH]: response(
        200,
        panels({
          panels: [
            panel({
              panel_serial: "482218012399",
              normalized_efficiency: 0.8,
              deviation_sigma: -2.5,
              is_underperforming: true,
            }),
          ],
        })
      ),
    });

    render(<PanelsPage />);

    expect(
      await screen.findByText(
        "482218012399: 20.0% below the fleet average (-2.50 sigma)"
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/microinverter fault/)).toBeInTheDocument();
  });

  it("omits the sigma when the fleet is too small to measure a spread", async () => {
    stubFetch({
      [PANELS_PATH]: response(
        200,
        panels({
          panels: [
            panel({ normalized_efficiency: 0.9, deviation_sigma: null }),
          ],
        })
      ),
    });

    render(<PanelsPage />);

    expect(
      await screen.findByTitle("482218012345: 10.0% below the fleet average")
    ).toBeInTheDocument();
  });

  it("explains an Enphase plan without per-panel data instead of erroring", async () => {
    stubFetch({
      [PANELS_PATH]: response(
        200,
        panels({
          panels: [],
          data_available: false,
          unavailable_reason:
            "Per-panel monitoring needs an Enphase plan that exposes microinverter data.",
        })
      ),
    });

    render(<PanelsPage />);

    expect(
      await screen.findByText("Per-panel data is not available yet")
    ).toBeInTheDocument();
    expect(
      screen.getByText(/needs an Enphase plan that exposes microinverter data/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Error:/)).not.toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    stubFetch({ [PANELS_PATH]: response(500, { detail: "boom" }) });

    render(<PanelsPage />);

    expect(await screen.findByText(/^Error: API error 500/)).toBeInTheDocument();
  });
});
