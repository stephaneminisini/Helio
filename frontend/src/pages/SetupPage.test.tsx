import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SystemSettings } from "../api/client";
import { SetupPage } from "./SetupPage";

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
  irradiance_source: "nrel",
};

function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

/** Stub fetch with one response per call, in order. */
function stubFetch(...responses: Response[]) {
  const fetchMock = vi.fn();
  responses.forEach((r) => fetchMock.mockResolvedValueOnce(r));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastBody(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown> {
  const [, options] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return JSON.parse((options as RequestInit).body as string);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SetupPage", () => {
  it("shows the onboarding form instead of an error when nothing is configured", async () => {
    stubFetch(response(404, { detail: "No system configured" }));

    render(<SetupPage />);

    expect(await screen.findByText(/Welcome to Helio/)).toBeInTheDocument();
    expect(screen.getByLabelText("Enphase System ID")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create System" })
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Error:/)).not.toBeInTheDocument();
  });

  it("creates the system and switches to edit mode", async () => {
    const fetchMock = stubFetch(
      response(404, { detail: "No system configured" }),
      response(201, SYSTEM)
    );
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
    const [url, options] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/settings");
    expect((options as RequestInit).method).toBe("POST");
    expect(lastBody(fetchMock)).toMatchObject({
      enphase_system_id: "test-001",
      install_date: "2022-06-15",
    });
    // Edit mode: the saved values are shown and the welcome copy is gone.
    expect(screen.queryByText(/Welcome to Helio/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("System Name")).toHaveValue("Roof Array");
    expect(screen.getByLabelText("Latitude")).toHaveValue(45.5231);
  });

  it("blocks submission with an inline message when a required field is empty", async () => {
    const fetchMock = stubFetch(response(404, { detail: "No system configured" }));
    render(<SetupPage />);
    await screen.findByText(/Welcome to Helio/);

    fireEvent.click(screen.getByRole("button", { name: "Create System" }));

    expect(
      await screen.findByText("Enphase System ID is required.")
    ).toBeInTheDocument();
    expect(screen.getByText("Install date is required.")).toBeInTheDocument();
    // Only the initial GET: no create request was sent.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the existing edit behaviour when a system is configured", async () => {
    const fetchMock = stubFetch(response(200, SYSTEM), response(200, SYSTEM));
    render(<SetupPage />);

    expect(
      await screen.findByRole("button", { name: "Save Settings" })
    ).toBeInTheDocument();
    expect(screen.queryByText(/Welcome to Helio/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Enphase System ID")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save Settings" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [, options] = fetchMock.mock.calls[1];
    expect((options as RequestInit).method).toBe("PUT");
    expect(lastBody(fetchMock)).toMatchObject({ name: "Roof Array" });
  });

  it("still shows an error state for a real API failure", async () => {
    stubFetch(response(500, { detail: "boom" }));

    render(<SetupPage />);

    expect(await screen.findByText(/^Error:/)).toBeInTheDocument();
    expect(screen.queryByText(/Welcome to Helio/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
