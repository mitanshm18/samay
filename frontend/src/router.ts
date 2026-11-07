// Hash routes: #/ (dashboard), #/new (check a bill), #/runs/<id> (one saved run),
// #/runs/<id>/optimisation and #/runs/<id>/calculation (the run's other tabs).

export type RunTab = "reconciliation" | "optimisation" | "calculation";
export type Route = { page: "dashboard" } | { page: "new" } | { page: "run"; id: number; tab: RunTab };

export function parseRoute(hash: string): Route {
  const run = /^#\/runs\/([1-9][0-9]{0,15})(?:\/(optimisation|calculation))?$/.exec(hash);
  if (run?.[1]) return { page: "run", id: Number(run[1]), tab: (run[2] as RunTab | undefined) ?? "reconciliation" };
  if (hash === "#/new") return { page: "new" };
  return { page: "dashboard" };
}

export function runHash(id: number, tab: RunTab = "reconciliation"): string {
  return tab === "reconciliation" ? `#/runs/${id}` : `#/runs/${id}/${tab}`;
}

export function go(hash: string): void {
  window.location.hash = hash;
}
