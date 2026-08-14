import { vi } from "vitest";

/** Build a minimal Response for the fields apiFetch reads. */
export function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

/**
 * Stub fetch, matching by path rather than call order so a component's own
 * requests cannot shift another component's expectations.
 *
 * A path may list several responses, which are returned one per call; the last
 * one is reused for any further calls. An unlisted path is an error, so a
 * forgotten route fails loudly instead of yielding undefined.
 */
export function stubFetch(routes: Record<string, Response | Response[]>) {
  const queues = new Map(
    Object.entries(routes).map(([path, value]) => [
      path,
      Array.isArray(value) ? [...value] : [value],
    ])
  );
  const fetchMock = vi.fn(async (url: string, _options?: RequestInit) => {
    const queue = queues.get(url);
    if (queue === undefined) throw new Error(`Unstubbed fetch: ${url}`);
    return queue.length > 1 ? (queue.shift() as Response) : queue[0];
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Return the calls a stubbed fetch received for one path. */
export function callsTo(
  fetchMock: ReturnType<typeof stubFetch>,
  path: string
): unknown[][] {
  return fetchMock.mock.calls.filter(([url]) => url === path);
}
