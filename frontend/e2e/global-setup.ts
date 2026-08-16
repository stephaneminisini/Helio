import { request } from "@playwright/test";

/** The API the dev server proxies to. Overridable for a non-default port. */
const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

const SETUP_HINT =
  "Start the stack and seed it first:\n" +
  "  make up && make migrate\n" +
  "  ./scripts/create-e2e-system.sh\n" +
  "  make seed-mock";

/**
 * Refuse to run unless the backend is up and holding seeded production data.
 *
 * Every spec asserts on rendered figures, so against an empty or absent backend
 * the whole suite fails on unrelated assertions and none of them say what is
 * actually wrong.
 *
 * @throws Error If the API cannot be reached, answers an error, or reports no
 *   stored production.
 */
export default async function globalSetup(): Promise<void> {
  const api = await request.newContext({ baseURL: API_URL });
  try {
    const health = await api.get("/api/health");
    if (!health.ok()) {
      throw new Error(
        `The API at ${API_URL} answered ${health.status()} on /api/health.\n${SETUP_HINT}`
      );
    }

    const overview = await api.get("/api/overview");
    if (!overview.ok()) {
      throw new Error(
        `The API at ${API_URL} answered ${overview.status()} on /api/overview.\n${SETUP_HINT}`
      );
    }

    const { all_time_kwh: allTime } = await overview.json();
    if (!allTime) {
      throw new Error(
        `The database behind ${API_URL} holds no production data.\n${SETUP_HINT}`
      );
    }
  } finally {
    await api.dispose();
  }
}
