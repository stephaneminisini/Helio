import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EnphaseStatus } from "../api/client";
import { response, stubFetch } from "../test/fetchStub";
import { EnphaseConnection } from "./EnphaseConnection";

const STATUS_PATH = "/api/auth/enphase/status";
const AUTHORIZE_PATH = "/api/auth/enphase/authorize";
const CONSENT_URL =
  "https://api.enphaseenergy.com/oauth/authorize?response_type=code" +
  "&client_id=client-id-123" +
  "&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fauth%2Fenphase%2Fcallback";

const CONNECTED: EnphaseStatus = {
  connected: true,
  client_configured: true,
  token_updated_at: "2026-08-01T04:00:00Z",
  last_successful_poll_at: "2026-08-13T04:01:00Z",
  token_warning: null,
};

const DISCONNECTED: EnphaseStatus = {
  connected: false,
  client_configured: true,
  token_updated_at: null,
  last_successful_poll_at: null,
  token_warning: null,
};

/** Put an OAuth callback outcome in the URL the component reads. */
function withOutcome(outcome: string) {
  window.history.pushState({}, "", `/?enphase=${outcome}`);
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

describe("EnphaseConnection", () => {
  it("links to the consent screen with the server's client ID and redirect URI", async () => {
    stubFetch({
      [STATUS_PATH]: response(200, DISCONNECTED),
      [AUTHORIZE_PATH]: response(200, { authorization_url: CONSENT_URL }),
    });

    render(<EnphaseConnection />);

    const link = await screen.findByRole("link", { name: "Connect to Enphase" });
    expect(link).toHaveAttribute("href", CONSENT_URL);
    expect(link.getAttribute("href")).toContain("client_id=client-id-123");
    expect(link.getAttribute("href")).toContain(
      "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fauth%2Fenphase%2Fcallback"
    );
  });

  it("shows the system as connected after a successful callback", async () => {
    withOutcome("connected");
    stubFetch({
      [STATUS_PATH]: response(200, CONNECTED),
      [AUTHORIZE_PATH]: response(200, { authorization_url: CONSENT_URL }),
    });

    render(<EnphaseConnection />);

    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(screen.getByText(/tokens are stored encrypted/i)).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "Reconnect to Enphase" })
    ).toBeInTheDocument();
  });

  it("explains that nothing was saved when the code exchange failed", async () => {
    withOutcome("exchange_failed");
    stubFetch({
      [STATUS_PATH]: response(200, DISCONNECTED),
      [AUTHORIZE_PATH]: response(200, { authorization_url: CONSENT_URL }),
    });

    render(<EnphaseConnection />);

    expect(
      await screen.findByText(/rejected the authorization code/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Nothing was saved/)).toBeInTheDocument();
    expect(screen.getByText("Not connected")).toBeInTheDocument();
  });

  it("shows the last successful poll time and no credentials", async () => {
    const fetchMock = stubFetch({
      [STATUS_PATH]: response(200, CONNECTED),
      [AUTHORIZE_PATH]: response(200, { authorization_url: CONSENT_URL }),
    });

    render(<EnphaseConnection />);
    await screen.findByText("Connected");

    const poll = new Date(CONNECTED.last_successful_poll_at as string);
    expect(
      screen.getByText(`Last successful poll: ${poll.toLocaleString()}`)
    ).toBeInTheDocument();
    // Reading the status must not require sending anything back.
    for (const [, options] of fetchMock.mock.calls) {
      expect((options as RequestInit | undefined)?.body).toBeUndefined();
    }
  });

  it("reports a system that has never polled", async () => {
    stubFetch({
      [STATUS_PATH]: response(200, DISCONNECTED),
      [AUTHORIZE_PATH]: response(200, { authorization_url: CONSENT_URL }),
    });

    render(<EnphaseConnection />);

    expect(await screen.findByText("Not connected")).toBeInTheDocument();
    expect(screen.getByText("Last successful poll: never")).toBeInTheDocument();
  });

  it("says what to configure when the server has no client credentials", async () => {
    stubFetch({
      [STATUS_PATH]: response(200, { ...DISCONNECTED, client_configured: false }),
    });

    render(<EnphaseConnection />);

    expect(await screen.findByText(/ENPHASE_CLIENT_ID/)).toBeInTheDocument();
    // Without credentials there is no consent URL to offer.
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
