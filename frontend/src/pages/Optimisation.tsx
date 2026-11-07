import { useEffect, useState } from "react";
import { ApiError, api, type Optimisation, type Recommendation } from "../api";
import { DemandGauge, PowerFactorDial, ZoneBar } from "../components/charts";
import { Badge } from "../components/values";
import { largestPaise } from "../format";

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: Optimisation };
type Filter = "all" | Recommendation["kind"];

const KIND: Record<Recommendation["kind"], { label: string; help: string }> = {
  actionable: { label: "Actionable", help: "The bill itself shows the problem." },
  indicative: { label: "Indicative", help: "A what-if scenario; its size is a stated assumption." },
  information: { label: "Information", help: "A finding with nothing to price." },
  "insufficient-data": { label: "Insufficient data", help: "Needed data is not on the bill." },
};

const CATEGORY: Record<Recommendation["category"], string> = {
  "peak-demand": "Peak demand",
  "contract-demand": "Contract demand",
  "load-shift": "Load shifting",
  "power-factor": "Power factor",
  "avoidable-charges": "Charges",
  "consumption-pattern": "Consumption pattern",
};

function CategoryIcon({ category }: { category: Recommendation["category"] }) {
  const paths: Record<Recommendation["category"], string> = {
    "peak-demand": "M3 17l5-6 4 3 6-9 3 4",
    "contract-demand": "M5 4h11l3 3v13H5zM8 10h8M8 14h8M8 18h5",
    "load-shift": "M4 8h13l-3-3M20 16H7l3 3",
    "power-factor": "M13 2L5 14h6l-1 8 8-12h-6z",
    "avoidable-charges": "M12 3v18M17 7H9.5a3 3 0 000 6h5a3 3 0 010 6H6",
    "consumption-pattern": "M3 20V10M9 20V4M15 20v-7M21 20v-11",
  };
  return (
    <svg className="cat-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={paths[category]} />
    </svg>
  );
}

function ConfidenceMeter({ level, reason }: { level: Recommendation["confidence"]; reason: string }) {
  const filled = level === "high" ? 3 : level === "medium" ? 2 : 1;
  return (
    <span className="confidence" title={reason}>
      <span className="confidence-bars" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span key={i} className={i <= filled ? "on" : ""} />
        ))}
      </span>
      {level[0]!.toUpperCase() + level.slice(1)} confidence
    </span>
  );
}

const STAMP: Record<Recommendation["saving"]["status"], string> = {
  illustrative: "Illustrative · synthetic tariff, not a real saving",
  estimated: "Estimated · verified tariff and readings",
  "insufficient-data": "Insufficient data",
  "not-applicable": "Not priced",
};

function SavingBlock({ item, scale }: { item: Recommendation; scale: string | null }) {
  const saving = item.saving;
  if (saving.amount) {
    // Bar width only (geometry): the saving against the largest saving on this bill.
    const width = scale ? Math.max(4, Math.min(100, (Number(saving.amount.paise) / Number(scale)) * 100)) : 0;
    return (
      <div className={`saving saving-${saving.status}`}>
        <span className="saving-label">
          {saving.status === "illustrative" ? "Illustrative saving per bill" : "Estimated saving per bill"}
        </span>
        <span className="saving-amount">{saving.amount.inr}</span>
        {saving.share_of_bill && <span className="saving-share">{saving.share_of_bill} of this bill</span>}
        <span className="impact" aria-hidden="true">
          <span style={{ width: `${width}%` }} />
        </span>
        <span className={`saving-stamp stamp-${saving.status}`}>
          {saving.status === "illustrative" ? "Synthetic tariff · not a real saving" : "Verified tariff and readings"}
        </span>
      </div>
    );
  }
  return (
    <div className={`saving saving-${saving.status}`}>
      <span className="saving-label">Saving</span>
      <span className="saving-amount muted-amount">
        {saving.status === "insufficient-data" ? "Insufficient data" : "Not priced"}
      </span>
      <span className="saving-share">
        {saving.status === "insufficient-data" ? "SAMAY does not guess a figure" : "a finding, not a ₹ saving"}
      </span>
    </div>
  );
}

export function RecommendationCard({ item, index, scale = null }: { item: Recommendation; index: number; scale?: string | null }) {
  const [open, setOpen] = useState(false);
  const hasDetail =
    item.basis.length + item.assumptions.length + item.missing_data.length + item.metrics.length > 0 ||
    item.saving.scenario !== null;
  return (
    <article className={`rec rec-${item.kind}`} style={{ animationDelay: `${index * 60}ms` }}>
      <header className="rec-head">
        <span className="rec-cat">
          <CategoryIcon category={item.category} />
          {CATEGORY[item.category]}
        </span>
        <span className={`kind kind-${item.kind}`} title={KIND[item.kind].help}>
          {KIND[item.kind].label}
        </span>
      </header>
      <div className="rec-body">
        <div className="rec-text">
          <h3>{item.title}</h3>
          <p className="rec-finding">{item.finding}</p>
          <p className="rec-action">
            <span>What to do</span>
            {item.action}
          </p>
        </div>
        <SavingBlock item={item} scale={scale} />
      </div>
      {item.kind === "insufficient-data" && item.missing_data.length > 0 && (
        <div className="needs">
          <span>To work this out, SAMAY needs</span>
          <ul>
            {item.missing_data.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      <footer className="rec-foot">
        <ConfidenceMeter level={item.confidence} reason={item.confidence_reason} />
        {hasDetail && (
          <button type="button" className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Hide the working" : "How this was worked out"}
          </button>
        )}
      </footer>
      {open && (
        <div className="rec-detail">
          <p className="small">
            <strong>Confidence:</strong> {item.confidence_reason}
          </p>
          {item.saving.scenario && (
            <div className="scenario">
              <div>
                <span>Current bill</span>
                <strong>{item.saving.current_total?.inr ?? "MISSING"}</strong>
              </div>
              <span className="arrow" aria-hidden="true">
                →
              </span>
              <div>
                <span>Scenario: {item.saving.scenario}</span>
                <strong>{item.saving.scenario_total?.inr ?? "Not calculable"}</strong>
              </div>
            </div>
          )}
          <p className="small muted">{item.saving.note}</p>
          {item.metrics.length > 0 && (
            <dl className="metrics">
              {item.metrics.map((m) => (
                <div key={m.label}>
                  <dt>{m.label}</dt>
                  <dd>{m.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {item.basis.length > 0 && (
            <>
              <h4>Calculation basis</h4>
              <ul>
                {item.basis.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </>
          )}
          {item.assumptions.length > 0 && (
            <>
              <h4>Assumptions</h4>
              <ul>
                {item.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </>
          )}
          {item.missing_data.length > 0 && (
            <>
              <h4>Missing data</h4>
              <ul>
                {item.missing_data.map((m) => (
                  <li key={m}>
                    <Badge tone="missing">MISSING</Badge> {m}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </article>
  );
}

export function OptimisationPanel({ runId }: { runId: number }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<"priority" | "saving">("priority");

  useEffect(() => {
    let live = true;
    setState({ kind: "loading" });
    api.optimisation(runId).then(
      (data) => live && setState({ kind: "ready", data }),
      (error: unknown) =>
        live &&
        setState({
          kind: "error",
          message: error instanceof ApiError ? error.message : "Could not analyse this bill.",
        }),
    );
    return () => {
      live = false;
    };
  }, [runId]);

  if (state.kind === "loading") {
    return (
      <div className="skeleton-stack" aria-busy="true" aria-label="Analysing">
        <div className="skeleton" />
        <div className="skeleton" />
        <div className="skeleton tall" />
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="alert alert-bad" role="alert">
        {state.message}
      </div>
    );
  }
  const data = state.data;
  const recs = data.recommendations;
  const count = (kind: Recommendation["kind"]) => data.counts[kind] ?? "0";
  const priced = recs.filter((r) => r.saving.amount !== null);
  const largest = largestPaise(priced.map((r) => r.saving.amount!.paise));
  const top = priced.find((r) => r.saving.amount!.paise === largest);
  const filtered = filter === "all" ? recs : recs.filter((r) => r.kind === filter);
  // Largest saving first, compared exactly as integers; unpriced items keep their order after.
  const shown =
    sort === "priority"
      ? filtered
      : [...filtered].sort((a, b) => {
          const x = a.saving.amount ? BigInt(a.saving.amount.paise) : null;
          const y = b.saving.amount ? BigInt(b.saving.amount.paise) : null;
          if (x === null || y === null) return x === null ? (y === null ? 0 : 1) : -1;
          return x === y ? 0 : x > y ? -1 : 1;
        });

  return (
    <div className="opt">
      {data.synthetic && (
        <div className="alert alert-synthetic" role="note">
          <Badge tone="synthetic">Synthetic tariff</Badge> Every ₹ figure in this section is
          illustrative: it is recalculated with {data.tariff.id}, whose rates are made up. It shows
          how each saving arises, not what a real plant would save.
        </div>
      )}

      <section className="opt-summary">
        <div className="opt-hero">
          <span className="eyebrow">Largest priced opportunity</span>
          {top ? (
            <>
              <span className={`opt-hero-amount${top.saving.status === "illustrative" ? " is-illustrative" : ""}`}>
                {top.saving.amount!.inr}
              </span>
              <span className="opt-hero-title">{top.title}</span>
              <span className={`saving-stamp stamp-${top.saving.status}`}>{STAMP[top.saving.status]}</span>
              <span className="opt-hero-tag">
                Per bill{top.saving.share_of_bill ? `, ${top.saving.share_of_bill} of this bill` : ""}. Each
                scenario is against the current bill alone, so savings are not added together.
              </span>
            </>
          ) : (
            <>
              <span className="opt-hero-amount muted-amount">Insufficient data</span>
              <span className="opt-hero-title">
                {data.current_total === null
                  ? "The bill total cannot be calculated, so no saving can be priced."
                  : "No opportunity on this bill can be priced."}
              </span>
            </>
          )}
        </div>
        <div className="opt-counts">
          {(["actionable", "indicative", "insufficient-data"] as const).map((kind) => (
            <div key={kind} className={`opt-count kind-${kind}`}>
              <span className="opt-count-value">{count(kind)}</span>
              <span className="opt-count-label">{KIND[kind].label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="viz-grid" aria-label="Consumption and demand">
        <DemandGauge profile={data.profile} />
        <ZoneBar profile={data.profile} />
        <PowerFactorDial profile={data.profile} />
        <div className="viz">
          <div className="viz-head">
            <span className="viz-title">Load factor</span>
            <span className="viz-sub">average load ÷ peak, over {data.profile.period_hours} h</span>
          </div>
          <div className="gauge-big">
            {data.profile.load_factor_percent ? (
              <span className="tone-accent">{data.profile.load_factor_percent}</span>
            ) : (
              <span className="badge badge-missing">Insufficient data</span>
            )}
            <small>higher means a steadier load</small>
          </div>
          <p className="viz-note">
            Energy {data.profile.kvah ? `${data.profile.kvah} kVAh` : "MISSING"} ·{" "}
            {data.profile.kwh ? `${data.profile.kwh} kWh` : "kWh MISSING"}
          </p>
        </div>
      </section>

      <section>
        <div className="section-head">
          <h2>Recommendations</h2>
          <div className="chips" role="tablist" aria-label="Filter recommendations">
            {(["all", "actionable", "indicative", "information", "insufficient-data"] as const).map((f) => (
              <button
                key={f}
                type="button"
                role="tab"
                aria-selected={filter === f}
                className={`chip${filter === f ? " on" : ""}`}
                onClick={() => setFilter(f)}
              >
                {f === "all" ? `All ${recs.length}` : `${KIND[f].label} ${count(f)}`}
              </button>
            ))}
          </div>
        </div>
        <div className="rec-tools">
          <ul className="saving-legend" aria-label="What the saving labels mean">
            <li>
              <span className="saving-stamp stamp-illustrative">Illustrative</span> recalculated with a synthetic
              tariff: shows how a saving arises, not a real figure
            </li>
            <li>
              <span className="saving-stamp stamp-estimated">Estimated</span> verified tariff and readings only
            </li>
            <li>
              <span className="saving-stamp stamp-insufficient-data">Insufficient data</span> an input is missing, so no
              figure is shown
            </li>
          </ul>
          <label className="sort">
            Sort
            <select value={sort} onChange={(e) => setSort(e.target.value as "priority" | "saving")}>
              <option value="priority">Priority (actionable first)</option>
              <option value="saving">Largest saving first</option>
            </select>
          </label>
        </div>
        <div className="recs">
          {shown.map((item, i) => (
            <RecommendationCard key={item.key} item={item} index={i} scale={largest} />
          ))}
          {shown.length === 0 && <p className="empty">Nothing in this group.</p>}
        </div>
      </section>
    </div>
  );
}
