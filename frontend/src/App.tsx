import { useEffect, useRef, useState } from "react";
import { api, type Health } from "./api";
import { Dashboard } from "./pages/Dashboard";
import { NewBill } from "./pages/NewBill";
import { RunView } from "./pages/RunView";
import { type Route, parseRoute } from "./router";

function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  const last = useRef(route);
  useEffect(() => {
    const update = () => {
      const next = parseRoute(window.location.hash);
      const prev = last.current;
      // Switching tabs inside one run keeps the scroll position; a new page starts at the top.
      const samePage = prev.page === "run" && next.page === "run" && prev.id === next.id;
      last.current = next;
      setRoute(next);
      if (!samePage) window.scrollTo?.(0, 0);
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}

function HealthDot() {
  const [health, setHealth] = useState<Health | "down" | null>(null);
  useEffect(() => {
    // Checked again every 10 seconds, so the badge shows when the API or database
    // stops and when it is back.
    let live = true;
    const check = () =>
      api.health().then(
        (h) => live && setHealth(h),
        () => live && setHealth("down"),
      );
    check();
    const timer = window.setInterval(check, 10_000);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);
  const up = health !== null && health !== "down";
  const text = health === null ? "Checking…" : up ? "API and database online" : "API or database offline";
  return (
    <span className={`health ${health === null ? "" : up ? "health-up" : "health-down"}`} role="status">
      <span className="dot" aria-hidden="true" />
      {text}
    </span>
  );
}

function Icon({ d }: { d: string }) {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export function App() {
  const route = useRoute();
  return (
    <div className="shell">
      <div className="backdrop" aria-hidden="true" />
      <aside className="sidebar">
        <a className="brand" href="#/">
          <span className="logo" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z" />
            </svg>
          </span>
          <span>
            <strong>SAMAY</strong>
            <small>Bill intelligence</small>
          </span>
        </a>
        <nav className="nav" aria-label="Main">
          <a href="#/" aria-current={route.page === "dashboard" ? "page" : undefined}>
            <Icon d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z" />
            Dashboard
          </a>
          <a href="#/new" aria-current={route.page === "new" ? "page" : undefined}>
            <Icon d="M12 16V4M7 9l5-5 5 5M4 20h16" />
            Check a bill
          </a>
          {route.page === "run" && (
            <a href={`#/runs/${route.id}`} aria-current="page" className="nav-sub">
              <Icon d="M6 3h9l4 4v14H6zM9 12h7M9 16h7" />
              Run #{route.id}
            </a>
          )}
        </nav>
        <div className="sidebar-foot">
          <HealthDot />
          <p>
            Every amount comes from SAMAY's calculation engine through the local API. The page does no
            arithmetic on money.
          </p>
        </div>
      </aside>
      <main className="content">
        <div key={route.page === "run" ? `run-${route.id}` : route.page} className="page-enter">
          {route.page === "dashboard" && <Dashboard />}
          {route.page === "new" && <NewBill />}
          {route.page === "run" && <RunView id={route.id} tab={route.tab} />}
        </div>
        <footer className="footer">
          SAMAY · Schneider Electric Yuva Yodha Hackathon 2026 · demo build. Sample bills and the
          SAMAY-DEMO-1 tariff are synthetic.
        </footer>
      </main>
    </div>
  );
}
