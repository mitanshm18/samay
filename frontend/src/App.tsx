import { useEffect, useState } from "react";
import { api, type Health } from "./api";
import { Dashboard } from "./pages/Dashboard";
import { NewBill } from "./pages/NewBill";
import { RunView } from "./pages/RunView";
import { type Route, parseRoute } from "./router";

function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const update = () => {
      setRoute(parseRoute(window.location.hash));
      window.scrollTo?.(0, 0);
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}

function HealthDot() {
  const [health, setHealth] = useState<Health | "down" | null>(null);
  useEffect(() => {
    let live = true;
    api.health().then(
      (h) => live && setHealth(h),
      () => live && setHealth("down"),
    );
    return () => {
      live = false;
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

export function App() {
  const route = useRoute();
  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#/">
          <span className="logo" aria-hidden="true">
            S
          </span>
          <span>
            <strong>SAMAY</strong>
            <small>Industrial electricity bill intelligence</small>
          </span>
        </a>
        <nav className="nav" aria-label="Main">
          <a href="#/" aria-current={route.page === "dashboard" ? "page" : undefined}>
            Dashboard
          </a>
          <a href="#/new" aria-current={route.page === "new" ? "page" : undefined}>
            Check a bill
          </a>
        </nav>
        <HealthDot />
      </header>
      <main className="content">
        {route.page === "dashboard" && <Dashboard />}
        {route.page === "new" && <NewBill />}
        {route.page === "run" && <RunView id={route.id} />}
      </main>
      <footer className="footer">
        Every amount on this page comes from SAMAY's calculation engine through the local API. The
        page itself does no arithmetic on money.
      </footer>
    </div>
  );
}
