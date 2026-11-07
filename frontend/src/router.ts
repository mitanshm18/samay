// Hash routes: #/ (dashboard), #/new (check a bill), #/runs/<id> (one saved run).

export type Route = { page: "dashboard" } | { page: "new" } | { page: "run"; id: number };

export function parseRoute(hash: string): Route {
  const run = /^#\/runs\/([1-9][0-9]{0,15})$/.exec(hash);
  if (run?.[1]) return { page: "run", id: Number(run[1]) };
  if (hash === "#/new") return { page: "new" };
  return { page: "dashboard" };
}

export function go(hash: string): void {
  window.location.hash = hash;
}
