import { useEffect, useState } from "react";
import { ApiError, api, type RunSummary } from "../api";
import { Badge, OutcomePill } from "../components/values";
import { dateTime, signedTone } from "../format";

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; runs: RunSummary[] };

function Money({ money, empty }: { money: RunSummary["totals"]["calculated"]; empty: string }) {
  if (money === null) return <Badge tone="missing">{empty}</Badge>;
  return <span className="amount">{money.inr}</span>;
}

function Difference({ run }: { run: RunSummary }) {
  if (run.command === "calculate") return <span className="muted">Not compared</span>;
  const money = run.totals.difference;
  if (money === null) return <Badge tone="missing">Not determinable</Badge>;
  const tone = signedTone(money.paise);
  return (
    <span className={`amount amount-${tone}`}>
      {tone === "positive" ? "+" : ""}
      {money.inr}
    </span>
  );
}

export function Dashboard() {
  const [state, setState] = useState<State>({ kind: "loading" });
  useEffect(() => {
    let live = true;
    api.runs().then(
      (runs) => live && setState({ kind: "ready", runs }),
      (error: unknown) =>
        live &&
        setState({
          kind: "error",
          message: error instanceof ApiError ? error.message : "Could not load the bill history.",
        }),
    );
    return () => {
      live = false;
    };
  }, []);

  const runs = state.kind === "ready" ? state.runs : [];
  const count = (outcome: RunSummary["outcome"]) => runs.filter((r) => r.outcome === outcome).length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Bill history</h1>
          <p className="lead">
            Every bill SAMAY has recalculated and compared with the utility's printed bill. Open a
            run to see each line, the totals and why they differ.
          </p>
        </div>
        <a className="button primary" href="#/new">
          Check a bill
        </a>
      </div>

      <section className="tiles" aria-label="Summary">
        <div className="tile">
          <span className="tile-label">Saved runs</span>
          <span className="tile-value">{state.kind === "ready" ? runs.length : "–"}</span>
        </div>
        <div className="tile tile-good">
          <span className="tile-label">Clean</span>
          <span className="tile-value">{state.kind === "ready" ? count("clean") : "–"}</span>
          <span className="tile-note">every line matches</span>
        </div>
        <div className="tile tile-bad">
          <span className="tile-label">Needs review</span>
          <span className="tile-value">{state.kind === "ready" ? count("not-clean") : "–"}</span>
          <span className="tile-note">differences or values not compared</span>
        </div>
        <div className="tile">
          <span className="tile-label">Calculated only</span>
          <span className="tile-value">{state.kind === "ready" ? count("calculated") : "–"}</span>
          <span className="tile-note">no printed bill compared</span>
        </div>
      </section>

      <section className="card">
        <h2>Saved runs</h2>
        {state.kind === "loading" && <p className="muted">Loading…</p>}
        {state.kind === "error" && (
          <div className="alert alert-bad" role="alert">
            {state.message}
          </div>
        )}
        {state.kind === "ready" && runs.length === 0 && (
          <p className="empty">
            No bills saved yet. <a href="#/new">Check your first bill</a>.
          </p>
        )}
        {state.kind === "ready" && runs.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Bill</th>
                  <th>Checked</th>
                  <th>Tariff</th>
                  <th className="num">Total payable (SAMAY)</th>
                  <th className="num">Printed total</th>
                  <th className="num">Difference</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    key={run.run_id}
                    className="clickable"
                    onClick={() => (window.location.hash = `#/runs/${run.run_id}`)}
                  >
                    <td>
                      <a href={`#/runs/${run.run_id}`}>#{run.run_id}</a>
                    </td>
                    <td className="strong">{run.bill_id}</td>
                    <td className="muted nowrap">{dateTime(run.created_at)}</td>
                    <td className="nowrap">
                      {run.tariff.id} {run.synthetic && <Badge tone="synthetic">Synthetic</Badge>}
                    </td>
                    <td className="num">
                      <Money money={run.totals.calculated} empty="MISSING" />
                    </td>
                    <td className="num">
                      {run.command === "calculate" ? (
                        <span className="muted">Not compared</span>
                      ) : (
                        <Money money={run.totals.printed} empty="Not given or missing" />
                      )}
                    </td>
                    <td className="num">
                      <Difference run={run} />
                    </td>
                    <td>
                      <OutcomePill outcome={run.outcome} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
