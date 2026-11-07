import { type ReactNode, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type Calculation,
  type Comparison,
  type Reconciliation,
  type RunDetail,
  type Traced,
  type Verify,
} from "../api";
import {
  Amount,
  Badge,
  EstimateNote,
  OutcomePill,
  QuantityValue,
  STATUS,
  StatusPill,
} from "../components/values";
import { dateTime, words } from "../format";

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; detail: RunDetail };

const EXPLANATION: Record<Reconciliation["explanation"]["state"], string> = {
  COMPLETE:
    "Every recalculated line was compared and every taken-as-printed amount is known, so the " +
    "total difference is fully explained by the line differences plus the printed bill's own " +
    "arithmetic (printed total minus the sum of its printed lines).",
  PARTIAL:
    "Only some lines could be compared. The differences below cover those lines only; SAMAY does " +
    "not guess the rest.",
  UNDETERMINABLE: "No line could be compared, so no difference can be explained.",
};

function Kpi({
  label,
  children,
  note,
  tone,
}: {
  label: string;
  children: ReactNode;
  note?: ReactNode;
  tone?: "good" | "bad" | "primary";
}) {
  return (
    <div className={`kpi${tone ? ` kpi-${tone}` : ""}`}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{children}</span>
      {note && <span className="kpi-note">{note}</span>}
    </div>
  );
}

function lineNote(line: Comparison): ReactNode {
  if (line.status === "NOT_RECALCULATED") return "Pass-through: included as printed, not checked.";
  if (line.status === "CALCULATED_ONLY") {
    return line.calculated?.value === null
      ? "Not on the printed bill, and SAMAY could not calculate it."
      : "Calculated by SAMAY but not on the printed bill.";
  }
  if (line.difference.value === null) {
    const reasons = line.difference.missing_reasons ?? [line.difference.note];
    return reasons.join("; ");
  }
  return STATUS[line.status].help;
}

function LineTable({ rec }: { rec: Reconciliation }) {
  return (
    <div className="table-wrap">
      <table className="table lines">
        <thead>
          <tr>
            <th>Line</th>
            <th className="num">Printed on bill</th>
            <th className="num">Recalculated by SAMAY</th>
            <th className="num">Difference (printed − SAMAY)</th>
            <th>Status</th>
            <th>Explanation</th>
          </tr>
        </thead>
        <tbody>
          {rec.lines.map((line) => (
            <tr key={line.code} className={`status-${line.status.toLowerCase()}`}>
              <td className="strong">{line.label}</td>
              <td className="num">
                <Amount value={line.printed} absent="Not on bill" missingLabel="ILLEGIBLE / MISSING" />
              </td>
              <td className="num">
                {line.status === "NOT_RECALCULATED" ? (
                  <span className="muted">Not recalculated</span>
                ) : (
                  <Amount value={line.calculated} absent="—" />
                )}
              </td>
              <td className="num">
                {line.status === "NOT_RECALCULATED" ? (
                  <span className="muted">Not checked</span>
                ) : line.difference.value === null ? (
                  <Badge tone="neutral">Not determinable</Badge>
                ) : (
                  <Amount value={line.difference} signed showEstimate={false} />
                )}
              </td>
              <td>
                <StatusPill status={line.status} />
              </td>
              <td className="small">
                {lineNote(line)}
                {line.rests_on_estimate && <EstimateNote bases={line.estimate_bases} />}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th>Total payable</th>
            <td className="num strong">
              {rec.total.printed_total_given ? (
                <Amount value={rec.total.printed} missingLabel="ILLEGIBLE / MISSING" />
              ) : (
                <span className="muted">Not given</span>
              )}
            </td>
            <td className="num strong">
              <Amount value={rec.total.calculated} />
            </td>
            <td className="num strong">
              {rec.total.difference.value === null ? (
                <Badge tone="neutral">Not determinable</Badge>
              ) : (
                <Amount value={rec.total.difference} signed showEstimate={false} />
              )}
            </td>
            <td colSpan={2} />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function Explanation({ rec }: { rec: Reconciliation }) {
  const ex = rec.explanation;
  const counts = rec.counts;
  return (
    <section className="card">
      <h2>Why the totals differ</h2>
      <p>
        <Badge tone={ex.state === "COMPLETE" ? "good" : "missing"}>{words(ex.state)} explanation</Badge>{" "}
        {EXPLANATION[ex.state]}
      </p>
      <dl className="facts">
        <div>
          <dt>Sum of differences on the {ex.compared_line_count} compared lines</dt>
          <dd>
            <Amount value={ex.compared_difference} signed showEstimate={false} />
          </dd>
        </div>
        <div>
          <dt>Printed total minus the sum of the printed lines</dt>
          <dd>
            <Amount value={rec.total.printed_lines_residual} signed showEstimate={false} missingLabel="Not determinable" />
          </dd>
        </div>
        <div>
          <dt>Total difference (printed − SAMAY)</dt>
          <dd>
            <Amount value={rec.total.difference} signed showEstimate={false} missingLabel="Not determinable" />
          </dd>
        </div>
        <div>
          <dt>Taken as printed (pass-through lines)</dt>
          <dd>
            {rec.counts.not_recalculated === "0" ? (
              <span className="muted">None on this bill</span>
            ) : (
              <Amount value={rec.taken_as_printed_total} />
            )}
          </dd>
        </div>
      </dl>
      <p className="muted small">
        {counts.match ?? "0"} match · {counts.differs ?? "0"} differ · {counts.calculated_only ?? "0"} not on
        bill · {counts.cannot_compare ?? "0"} cannot compare · {counts.not_recalculated ?? "0"} taken as printed.
        A matching total never implies matching lines: the comparison is to the paisa, line by line.
      </p>
      {ex.not_compared.length > 0 && (
        <>
          <h3>Lines not compared</h3>
          <ul className="issues">
            {ex.not_compared.map((item) => (
              <li key={item.code}>
                <StatusPill status={item.status} /> <strong>{item.label}</strong>: {item.reason}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function Breakdown({ calc }: { calc: Calculation }) {
  return (
    <section className="card">
      <details open>
        <summary>
          <h2>Calculation breakdown</h2>
        </summary>
        <h3>Inputs and quantities</h3>
        <div className="table-wrap">
          <table className="table compact">
            <thead>
              <tr>
                <th>Quantity</th>
                <th className="num">Value</th>
                <th>Source</th>
                <th>How</th>
              </tr>
            </thead>
            <tbody>
              {calc.quantities.map((q) => (
                <tr key={q.key}>
                  <td className="strong">{q.label}</td>
                  <td className="num">
                    <QuantityValue value={q} />
                    {q.rests_on_estimate && <EstimateNote bases={q.estimate_bases} />}
                  </td>
                  <td>
                    <Provenance value={q} />
                  </td>
                  <td className="small">{q.formula === "read" ? q.note : q.formula}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3>Charges</h3>
        <div className="table-wrap">
          <table className="table compact">
            <thead>
              <tr>
                <th>Line</th>
                <th>Formula</th>
                <th>Rounding</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {calc.lines.map((line) => (
                <tr key={`${line.code}-${line.label}`}>
                  <td className="strong">
                    {line.label}
                    {line.basis !== "recalculated" && (
                      <>
                        {" "}
                        <Badge tone="passthrough">Taken as printed</Badge>
                      </>
                    )}
                  </td>
                  <td className="small">{line.formula}</td>
                  <td className="small nowrap">{line.rounding ?? "—"}</td>
                  <td className="num">
                    <Amount value={line.amount} />
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th colSpan={3}>Subtotal</th>
                <td className="num">
                  <Amount value={calc.subtotal} />
                </td>
              </tr>
              <tr>
                <th colSpan={3}>Total payable (sum of all lines)</th>
                <td className="num strong">
                  <Amount value={calc.total} />
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
        {calc.assumptions.length > 0 && (
          <>
            <h3>Assumptions</h3>
            <ul className="assumptions">
              {calc.assumptions.map((a) => (
                <li key={a.key}>{a.text}</li>
              ))}
            </ul>
          </>
        )}
      </details>
    </section>
  );
}

function Provenance({ value }: { value: Traced }) {
  if (value.provenance === "estimated") return <Badge tone="estimated">Estimated</Badge>;
  if (value.provenance === "missing") return <Badge tone="missing">Missing</Badge>;
  return <span className="muted small">{words(value.provenance)}</span>;
}

export function RunView({ id }: { id: number }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [verify, setVerify] = useState<Verify | "busy" | { error: string } | null>(null);

  useEffect(() => {
    let live = true;
    setState({ kind: "loading" });
    setVerify(null);
    api.run(id).then(
      (detail) => live && setState({ kind: "ready", detail }),
      (error: unknown) =>
        live &&
        setState({
          kind: "error",
          message: error instanceof ApiError ? error.message : "Could not load this run.",
        }),
    );
    return () => {
      live = false;
    };
  }, [id]);

  if (state.kind === "loading") return <p className="muted">Loading run #{id}…</p>;
  if (state.kind === "error") {
    return (
      <div className="alert alert-bad" role="alert">
        {state.message} <a href="#/">Back to the dashboard</a>
      </div>
    );
  }

  const { run, report } = state.detail;
  const rec = report.reconciliation;
  const calc = report.calculation;

  const onVerify = async () => {
    setVerify("busy");
    try {
      setVerify(await api.verify(id));
    } catch (error) {
      setVerify({ error: error instanceof ApiError ? error.message : "Verification failed." });
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <a href="#/">Dashboard</a> / Run #{run.run_id}
          </p>
          <h1>
            Bill {run.bill_id} <OutcomePill outcome={run.outcome} />
          </h1>
          <p className="lead">
            {report.tariff.name} · checked {dateTime(run.created_at)} ·{" "}
            {run.command === "reconcile" ? "recalculated and reconciled" : "recalculated only"}
          </p>
        </div>
        <div className="row">
          <button type="button" onClick={onVerify} disabled={verify === "busy"}>
            {verify === "busy" ? "Verifying…" : "Verify saved report"}
          </button>
          <a className="button ghost" href={api.reportUrl(run.run_id)} download={`samay-run-${run.run_id}-report.json`}>
            Report JSON
          </a>
          <a className="button ghost" href={api.sourceUrl(run.run_id)} download={`samay-run-${run.run_id}-bill.json`}>
            Bill file
          </a>
        </div>
      </div>

      {report.banner && (
        <div className="alert alert-synthetic" role="note">
          <Badge tone="synthetic">Synthetic</Badge> {report.banner}
        </div>
      )}

      {verify !== null && verify !== "busy" && (
        <div
          className={`alert ${"error" in verify ? "alert-bad" : verify.matches ? "alert-good" : "alert-bad"}`}
          role="status"
        >
          {"error" in verify
            ? verify.error
            : `${verify.message} (report SHA-256 ${verify.recomputed_sha256.slice(0, 12)}…)`}
        </div>
      )}

      <div className={`alert ${run.outcome === "clean" ? "alert-good" : run.outcome === "not-clean" ? "alert-warn" : "alert-neutral"}`}>
        <strong>
          {run.outcome === "clean" ? "Clean" : run.outcome === "not-clean" ? "Needs review" : "Calculated only"}.
        </strong>{" "}
        {run.outcome_text}
      </div>

      <section className="kpis" aria-label="Totals">
        <Kpi label="Total payable (recalculated by SAMAY)" tone="primary" note={calc.complete ? "sum of all lines" : "incomplete: inputs missing"}>
          <Amount value={calc.total} />
        </Kpi>
        {rec ? (
          <>
            <Kpi label="Printed total on bill">
              {rec.total.printed_total_given ? (
                <Amount value={rec.total.printed} missingLabel="ILLEGIBLE / MISSING" />
              ) : (
                <span className="muted">Not given</span>
              )}
            </Kpi>
            <Kpi
              label="Difference (printed − SAMAY)"
              tone={rec.total.difference.paise === "0" ? "good" : rec.total.difference.value === null ? undefined : "bad"}
            >
              <Amount value={rec.total.difference} signed showEstimate={false} missingLabel="Not determinable" />
            </Kpi>
            <Kpi label="Line comparison" tone={rec.clean ? "good" : "bad"} note={`${rec.explanation.compared_line_count} lines compared`}>
              {rec.counts.differs ?? "0"} differ · {rec.counts.cannot_compare ?? "0"} not comparable
            </Kpi>
          </>
        ) : (
          <>
            <Kpi label="Subtotal">
              <Amount value={calc.subtotal} />
            </Kpi>
            <Kpi label="Taken as printed">
              {calc.taken_as_printed.line_count === "0" ? (
                <span className="muted">None on this bill</span>
              ) : (
                <Amount value={calc.taken_as_printed.total} />
              )}
            </Kpi>
          </>
        )}
      </section>

      {rec && (
        <section className="card">
          <h2>Line by line: printed bill vs SAMAY</h2>
          <p className="legend small">
            <Badge tone="missing">MISSING</Badge> a value that is not available (never shown as zero) ·{" "}
            <Badge tone="estimated">ESTIMATED</Badge> rests on an estimate ·{" "}
            <Badge tone="passthrough">Taken as printed</Badge> pass-through, not recalculated
          </p>
          <LineTable rec={rec} />
        </section>
      )}

      {rec && <Explanation rec={rec} />}

      <Breakdown calc={calc} />

      {report.warnings.length > 0 && (
        <section className="card">
          <h2>Warnings</h2>
          <ul className="issues">
            {report.warnings.map((w, i) => (
              <li key={`${w.code}-${i}`}>
                <Badge tone={w.code === "input-estimated" ? "estimated" : w.code.includes("missing") ? "missing" : "neutral"}>
                  {w.code}
                </Badge>{" "}
                {w.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="muted small">
        Engine {state.detail.engine_version} · bill SHA-256 {state.detail.source_sha256.slice(0, 12)}… · report
        SHA-256 {state.detail.report_sha256.slice(0, 12)}…
      </p>
    </>
  );
}
