import { useEffect, useState } from "react";
import { EnphaseStatus, api } from "../api/client";

/**
 * Outcomes the OAuth callback reports through the ?enphase= query parameter.
 * The wording lives here rather than in the redirect so nothing an external
 * caller controls is rendered back to the user.
 */
const CALLBACK_MESSAGES: Record<string, string> = {
  connected: "Enphase account connected. The tokens are stored encrypted.",
  denied:
    "Enphase did not return an authorization code, so nothing was connected. Try again.",
  exchange_failed:
    "Enphase rejected the authorization code - it may have expired or already been used. Nothing was saved; try connecting again.",
  not_configured:
    "The server has no Enphase client credentials. Set ENPHASE_CLIENT_ID and ENPHASE_CLIENT_SECRET in .env, then restart the API.",
  no_system: "Save your system settings first, then connect to Enphase.",
};

function formatTimestamp(value: string | null): string {
  return value === null ? "never" : new Date(value).toLocaleString();
}

/** Connection status for the Enphase account, with a link to (re)connect. */
export function EnphaseConnection() {
  const [status, setStatus] = useState<EnphaseStatus | null>(null);
  const [consentUrl, setConsentUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const outcome = new URLSearchParams(window.location.search).get("enphase");

  useEffect(() => {
    api
      .getEnphaseStatus()
      .then(async (fetched) => {
        setStatus(fetched);
        // Asking for a consent URL without credentials returns a 503, and the
        // status already explains that case.
        if (!fetched.client_configured) return;
        const { authorization_url } = await api.getEnphaseConsentUrl();
        setConsentUrl(authorization_url);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <section className="space-y-3 border-t border-gray-800 pt-6">
      <h2 className="text-lg font-semibold text-white">Connect to Enphase</h2>
      {outcome && CALLBACK_MESSAGES[outcome] && (
        <p
          className={
            outcome === "connected"
              ? "text-sm text-green-400"
              : "text-sm text-red-400"
          }
        >
          {CALLBACK_MESSAGES[outcome]}
        </p>
      )}
      {error && <p className="text-sm text-red-400">Error: {error}</p>}
      {status && (
        <div className="space-y-1 text-sm text-gray-400">
          <p>
            Status:{" "}
            <span className={status.connected ? "text-green-400" : "text-gray-300"}>
              {status.connected ? "Connected" : "Not connected"}
            </span>
          </p>
          <p>Last successful poll: {formatTimestamp(status.last_successful_poll_at)}</p>
          {status.connected && (
            <p>Tokens last rotated: {formatTimestamp(status.token_updated_at)}</p>
          )}
          {status.token_warning && (
            <p className="text-yellow-400">{status.token_warning}</p>
          )}
          {!status.client_configured && (
            <p className="text-red-400">{CALLBACK_MESSAGES.not_configured}</p>
          )}
        </div>
      )}
      {consentUrl && (
        <a
          href={consentUrl}
          className="inline-block bg-solar-500 hover:bg-solar-600 text-white font-medium px-6 py-2 rounded-lg text-sm"
        >
          {status?.connected ? "Reconnect to Enphase" : "Connect to Enphase"}
        </a>
      )}
    </section>
  );
}
