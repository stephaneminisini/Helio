import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EnphaseStatus, SystemSettings } from "../api/client";
import { callsTo, response, stubFetch } from "../test/fetchStub";
import { SetupPage } from "./SetupPage";

const SETTINGS_PATH = "/api/settings";
const STATUS_PATH = "/api/auth/enphase/status";

const SYSTEM: SystemSettings = {
  enphase_system_id: "test-001",
  name: "Roof Array",
  location: "Portland, OR",
  latitude: "45.523100",
  longitude: "-122.676500",
  system_size_kw: "10.000",
  panel_count: 25,
  panel_wattage_w: 400,
  install_date: "2022-06-15",
  tilt_angle_deg: "30.00",
  azimuth_deg: "180.00",
  degradation_rate: "0.500",
  warranty_degradation_rate: "0.700",
  energy_rate_per_kwh: "0.1500",
  energy_rate_currency: "USD",
  irradiance_source: "nrel",
  enphase_connected: false,
};

const DISCONNECTED: EnphaseStatus = {
  connected: false,
  client_configured: false,
  token_updated_at: null,
  last_successful_poll_at: null,
  token_warning: null,
};

function jsonBody(call: unknown[]): Record<string, unknown> {
  const [, options] = call as [string, RequestInit];
  return JSON.parse(options.body as string);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SetupPage", () => {
  it("shows the onboarding form instead of an error when nothing is configured", async () => {
    stubFetch({ [SETTINGS_PATH]: response(404, { detail: "No system configured" }) });

    render(<SetupPage />);

    expect(await screen.findByText(/Welcome to Helio/)).toBeInTheDocument();
    expect(screen.getByLabelText("Enphase System ID")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create System" })
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Error:/)).not.toBeInTheDocument();
  });

  it("creates the system and switches to edit mode", async () => {
    const fetchMock = stubFetch({
      [SETTINGS_PATH]: [
        response(404, { detail: "No system configured" }),
        response(201, SYSTEM),
      ],
      [STATUS_PATH]: response(200, DISCONNECTED),
    });
    render(<SetupPage />);
    await screen.findByText(/Welcome to Helio/);

    fireEvent.change(screen.getByLabelText("Enphase System ID"), {
      target: { value: "test-001" },
    });
    fireEvent.change(screen.getByLabelText("Install Date"), {
      target: { value: "2022-06-15" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create System" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save Settings" })).toBeEnabled()
    );
    const create = callsTo(fetchMock, SETTINGS_PATH)[1];
    expect((create[1] as RequestInit).method).toBe("POST");
    expect(jsonBody(create)).toMatchObject({
      enphase_system_id: "test-001",
      install_date: "2022-06-15",
    });
    // Edit mode: the saved values are shown and the welcome copy is gone.
    expect(screen.queryByText(/Welcome to Helio/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("System Name")).toHaveValue("Roof Array");
    expect(screen.getByLabelText("Latitude")).toHaveValue(45.5231);
  });

  it("blocks submission with an inline message when a required field is empty", async () => {
    const fetchMock = stubFetch({
      [SETTINGS_PATH]: response(404, { detail: "No system configured" }),
    });
    render(<SetupPage />);
    await screen.findByText(/Welcome to Helio/);

    fireEvent.click(screen.getByRole("button", { name: "Create System" }));

    expect(
      await screen.findByText("Enphase System ID is required.")
    ).toBeInTheDocument();
    expect(screen.getByText("Install date is required.")).toBeInTheDocument();
    // Only the initial GET: no create request was sent.
    expect(callsTo(fetchMock, SETTINGS_PATH)).toHaveLength(1);
  });

  it("keeps the existing edit behaviour when a system is configured", async () => {
    const fetchMock = stubFetch({
      [SETTINGS_PATH]: [response(200, SYSTEM), response(200, SYSTEM)],
      [STATUS_PATH]: response(200, DISCONNECTED),
    });
    render(<SetupPage />);

    expect(
      await screen.findByRole("button", { name: "Save Settings" })
    ).toBeInTheDocument();
    expect(screen.queryByText(/Welcome to Helio/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Enphase System ID")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save Settings" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, SETTINGS_PATH)).toHaveLength(2)
    );
    const update = callsTo(fetchMock, SETTINGS_PATH)[1];
    expect((update[1] as RequestInit).method).toBe("PUT");
    expect(jsonBody(update)).toMatchObject({ name: "Roof Array" });
  });

  it("sends the warranty threshold and energy rate, normalising the currency", async () => {
    const fetchMock = stubFetch({
      [SETTINGS_PATH]: [response(200, SYSTEM), response(200, SYSTEM)],
      [STATUS_PATH]: response(200, DISCONNECTED),
    });
    render(<SetupPage />);
    await screen.findByRole("button", { name: "Save Settings" });

    fireEvent.change(screen.getByLabelText("Warranty Threshold (%/yr)"), {
      target: { value: "0.5" },
    });
    fireEvent.change(screen.getByLabelText("Energy Rate (per kWh)"), {
      target: { value: "0.235" },
    });
    // The API only accepts an uppercase ISO 4217 code.
    fireEvent.change(screen.getByLabelText("Currency"), {
      target: { value: "eur" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Settings" }));

    await waitFor(() => expect(callsTo(fetchMock, SETTINGS_PATH)).toHaveLength(2));
    expect(jsonBody(callsTo(fetchMock, SETTINGS_PATH)[1])).toMatchObject({
      warranty_degradation_rate: "0.5",
      energy_rate_per_kwh: "0.235",
      energy_rate_currency: "EUR",
    });
  });

  it("still shows an error state for a real API failure", async () => {
    stubFetch({ [SETTINGS_PATH]: response(500, { detail: "boom" }) });

    render(<SetupPage />);

    expect(await screen.findByText(/^Error:/)).toBeInTheDocument();
    expect(screen.queryByText(/Welcome to Helio/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers the Enphase connection section once a system exists", async () => {
    stubFetch({
      [SETTINGS_PATH]: response(200, SYSTEM),
      [STATUS_PATH]: response(200, DISCONNECTED),
    });

    render(<SetupPage />);

    expect(
      await screen.findByRole("heading", { name: "Connect to Enphase" })
    ).toBeInTheDocument();
  });
});
