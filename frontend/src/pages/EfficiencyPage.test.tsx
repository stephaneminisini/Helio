import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EfficiencyData } from "../api/client";
import { response, stubFetch } from "../test/fetchStub";
import { EfficiencyPage } from "./EfficiencyPage";

const EFFICIENCY_PATH = "/api/efficiency";

function efficiency(
  overrides: Partial<EfficiencyData["degradation"]> = {}
): EfficiencyData {
  return {
    pr_history: [],
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
});
