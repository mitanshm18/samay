import { useEffect, useState } from "react";
import { ApiError, api, type Optimisation, type RunSummary } from "../api";
import { CountUp, HistoryChart } from "../components/charts";
import { Badge, OutcomePill } from "../components/values";
import { dateTime, largestPaise, signedTone } from "../format";

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

  const ready = state.kind === "ready";
  const tile = (value: number) => (ready ? <CountUp value={value} /> : "–");
  const latest = runs[0];

  if (ready && runs.length === 0) return <FirstRun />;

  return (
    <>
      <section className="hero">
        <div className="hero-text">
          <span className="eyebrow">Industrial electricity bill intelligence</span>
          <h1>Every line of the bill, recalculated to the paisa.</h1>
          <p className="lead">
            SAMAY rebuilds each charge from the tariff, compares it with the utility's printed bill,
            explains every difference and finds where the next bill could cost less. Missing data is
            shown as missing, never as zero.
          </p>
          <div className="row">
            <a className="button primary" href="#/new">
              Check a bill
            </a>
            {latest && (
              <a className="button ghost" href={`#/runs/${latest.run_id}/optimisation`}>
                Cost optimisation for run #{latest.run_id}
              </a>
            )}
          </div>
        </div>
        <div className="hero-chart">
          <div className="hero-chart-head">
            <span>Total payable of recent runs</span>
            <span className="muted small">hover or tab to a bar · click to open</span>
          </div>
          {ready ? (
            <HistoryChart runs={runs} />
          ) : (
            <div className={`history-empty${state.kind === "loading" ? " skeleton" : ""}`}>
              {state.kind === "error" ? "History unavailable" : ""}
            </div>
          )}
          <div className="hero-legend small">
            <span>
              <i className="sw sw-clean" /> clean
            </span>
            <span>
              <i className="sw sw-not-clean" /> needs review
            </span>
            <span>
              <i className="sw sw-calculated" /> calculated only
            </span>
            <span>
              <i className="sw sw-missing" /> total MISSING
            </span>
          </div>
        </div>
      </section>

      {state.kind === "error" && (
        <div className="alert alert-bad" role="alert">
          {state.message}
        </div>
      )}

      <div className="split">
        <section className="zone-audit" aria-labelledby="audit-head">
          <div className="zone-head">
            <span className="zone-tag tag-audit">Audit</span>
            <h2 id="audit-head">What the bills say</h2>
            <span className="muted small">recalculated and compared with the printed bill</span>
          </div>
          <div className="tiles" aria-label="Summary">
            <a className="tile" href="#history">
              <span className="tile-label">Saved runs</span>
              <span className="tile-value">{tile(runs.length)}</span>
              <span className="tile-note">each saved exactly as entered</span>
            </a>
            <div className="tile tile-good">
              <span className="tile-label">Clean</span>
              <span className="tile-value">{tile(count("clean"))}</span>
              <span className="tile-note">every line matches</span>
            </div>
            <div className="tile tile-bad">
              <span className="tile-label">Needs review</span>
              <span className="tile-value">{tile(count("not-clean"))}</span>
              <span className="tile-note">differences or values not compared</span>
            </div>
            <div className="tile">
              <span className="tile-label">Calculated only</span>
              <span className="tile-value">{tile(count("calculated"))}</span>
              <span className="tile-note">no printed bill compared</span>
            </div>
          </div>
        </section>
        <section className="zone-insight" aria-labelledby="insight-head">
          <div className="zone-head">
            <span className="zone-tag tag-insight">Optimisation</span>
            <h2 id="insight-head">Where the next bill could cost less</h2>
          </div>
          {latest ? <LatestInsight run={latest} /> : <div className="skeleton tall" />}
        </section>
      </div>

      <section className="card" id="history">
        <div className="section-head">
          <h2>Bill history</h2>
          <span className="muted small">newest first · click a row to open the run</span>
        </div>
        {state.kind === "loading" && (
          <div className="skeleton-stack" aria-busy="true" aria-label="Loading">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        )}
        {state.kind === "error" && <p className="empty">The bill history appears here once the API and database are running.</p>}
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
                    className={`clickable row-${run.outcome}`}
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

function FirstRun() {
  return (
    <section className="first-run">
      <span className="eyebrow">Welcome to SAMAY</span>
      <h1>No bills checked yet.</h1>
      <p className="lead">
        Check a bill to see every charge recalculated, compared with the printed bill and analysed
        for savings. Nothing here is made up: the history fills with the bills you check.
      </p>
      <ol className="first-steps">
        <li>
          <b>1</b> Upload a <code>samay.bill/1</code> file or pick a sample bill
        </li>
        <li>
          <b>2</b> Validate it: every problem is listed, nothing is saved
        </li>
        <li>
          <b>3</b> Calculate, reconcile and save, then open Cost optimisation
        </li>
      </ol>
      <a className="button primary" href="#/new">
        Check your first bill
      </a>
    </section>
  );
}

type Insight = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: Optimisation };

/** The latest run's optimisation, as the API reports it. Nothing is added up here. */
function LatestInsight({ run }: { run: RunSummary }) {
  const [state, setState] = useState<Insight>({ kind: "loading" });
  useEffect(() => {
    let live = true;
    api.optimisation(run.run_id).then(
      (data) => live && setState({ kind: "ready", data }),
      (error: unknown) =>
        live &&
        setState({ kind: "error", message: error instanceof ApiError ? error.message : "Could not analyse the bill." }),
    );
    return () => {
      live = false;
    };
  }, [run.run_id]);

  if (state.kind === "loading") return <div className="skeleton tall" aria-busy="true" aria-label="Analysing" />;
  if (state.kind === "error") return <p className="empty">{state.message}</p>;
  const data = state.data;
  const priced = data.recommendations.filter((r) => r.saving.amount !== null);
  const top = largestPaise(priced.map((r) => r.saving.amount!.paise));
  const best = priced.find((r) => r.saving.amount!.paise === top);
  const illustrative = best?.saving.status === "illustrative";
  return (
    <a className="insight" href={`#/runs/${run.run_id}/optimisation`}>
      <span className="insight-sub">
        Latest bill: <strong>{data.bill_id}</strong> · run #{run.run_id}
      </span>
      {best ? (
        <>
          <span className={`insight-amount${illustrative ? " is-illustrative" : ""}`}>{best.saving.amount!.inr}</span>
          <span className="insight-title">{best.title}</span>
          <span className={`saving-stamp stamp-${best.saving.status}`}>
            {illustrative ? "Illustrative · synthetic tariff, not a real saving" : "Estimated with a verified tariff"}
          </span>
        </>
      ) : (
        <>
          <span className="insight-amount muted-amount">Insufficient data</span>
          <span className="insight-title">No saving on this bill can be priced from the data on it.</span>
        </>
      )}
      <span className="insight-counts">
        <span className="kind kind-actionable">{data.counts.actionable ?? "0"} actionable</span>
        <span className="kind kind-indicative">{data.counts.indicative ?? "0"} indicative</span>
        <span className="kind kind-insufficient-data">{data.counts["insufficient-data"] ?? "0"} need data</span>
      </span>
      <span className="insight-cta">Open cost optimisation →</span>
    </a>
  );
}
