import { vi } from "vitest";

/** Answer fetch calls from a map of path -> [status, body]. */
export function mockApi(routes: Record<string, [number, unknown]>) {
  const fetch = vi.fn(async (path: string) => {
    const route = routes[path];
    if (!route) return new Response(JSON.stringify({ error: "x", message: `no mock for ${path}` }), { status: 404 });
    return new Response(JSON.stringify(route[1]), { status: route[0] });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
