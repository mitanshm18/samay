// Small SVG charts. Geometry only: Number() is used to size bars and needles from the
// API's quantity and paise strings. Every number a person reads is the API's own text.

import { useEffect, useState } from "react";
import type { Optimisation, RunSummary } from "../api";
import { quantity } from "../format";

type Profile = Optimisation["profile"];

function num(text: string | null | undefined): number | null {
  if (text === null || text === undefined) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

/** An integer that counts up once on first render (counts only, never money). */
export function CountUp({ value }: { value: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (typeof window === "undefined" || !window.requestAnimationFrame || value === 0) {
      setShown(value);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 700);
      setShown(Math.round(value * (1 - (1 - t) ** 3)));
      if (t < 1) frame = window.requestAnimationFrame(step);
    };
    frame = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(frame);
  }, [value]);
  return <>{shown}</>;
}

const ZONE_LABEL = { peak: "Peak", normal: "Normal", off_peak: "Off-peak" } as const;
const ZONE_ORDER = ["peak", "normal", "off_peak"] as const;

export function ZoneBar({ profile }: { profile: Profile }) {
  const zones = ZONE_ORDER.map((zone) => profile.zones.find((z) => z.zone === zone)!);
  const missing = zones.filter((z) => z.kvah === null);
  const total = zones.reduce((sum, z) => sum + (num(z.kvah) ?? 0), 0);
  return (
    <div className="viz">
      <div className="viz-head">
        <span className="viz-title">Time-of-day energy</span>
        <span className="viz-sub">kVAh by tariff zone</span>
      </div>
      {missing.length > 0 || total === 0 ? (
        <div className="viz-empty">
          <span className="badge badge-missing">Insufficient data</span>
          <span>
            {missing.length > 0
              ? `${missing.map((z) => ZONE_LABEL[z.zone]).join(", ")} reading not on the bill`
              : "No energy recorded"}
          </span>
        </div>
      ) : (
        <div className="zonebar" role="img" aria-label="Energy split by time-of-day zone">
          {zones.map((z) => (
            <span
              key={z.zone}
              className={`zone zone-${z.zone}`}
              style={{ flexGrow: num(z.kvah) ?? 0 }}
              title={`${ZONE_LABEL[z.zone]} ${z.hours}: ${quantity(z.kvah ?? "0", "kVAh")}`}
            />
          ))}
        </div>
      )}
      <ul className="zone-legend">
        {zones.map((z) => (
          <li key={z.zone}>
            <span className={`swatch zone-${z.zone}`} aria-hidden="true" />
            <span className="zone-name">
              {ZONE_LABEL[z.zone]} <small>{z.hours}</small>
            </span>
            <span className="zone-value">
              {z.kvah === null ? <span className="badge badge-missing">MISSING</span> : quantity(z.kvah, "kVAh")}
              {z.percent && <small>{z.percent}</small>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DemandGauge({ profile }: { profile: Profile }) {
  const cd = num(profile.contract_demand_kva);
  const md = num(profile.recorded_md_kva);
  const floor = num(profile.demand_floor_kva);
  if (cd === null || md === null) {
    return (
      <div className="viz">
        <div className="viz-head">
          <span className="viz-title">Maximum demand</span>
          <span className="viz-sub">against contract demand</span>
        </div>
        <div className="viz-empty">
          <span className="badge badge-missing">Insufficient data</span>
          <span>Contract demand and recorded maximum demand are both needed.</span>
        </div>
      </div>
    );
  }
  const scale = Math.max(cd, md) * 1.15 || 1;
  const pct = (v: number) => `${Math.min(100, (v / scale) * 100)}%`;
  const over = md > cd;
  return (
    <div className="viz">
      <div className="viz-head">
        <span className="viz-title">Maximum demand</span>
        <span className="viz-sub">against contract demand</span>
      </div>
      <div className="gauge-big">
        <span className={over ? "tone-bad" : "tone-accent"}>{quantity(profile.recorded_md_kva!, "kVA")}</span>
        <small>{over ? "above contract" : "recorded peak"}</small>
      </div>
      <div className="demand" role="img" aria-label="Maximum demand against contract demand">
        <div className={`demand-fill${over ? " over" : ""}`} style={{ width: pct(md) }} />
        {floor !== null && (
          <span className="demand-mark mark-floor" style={{ left: pct(floor) }} title="Billing floor" />
        )}
        <span className="demand-mark mark-cd" style={{ left: pct(cd) }} title="Contract demand" />
      </div>
      <dl className="demand-legend">
        <div>
          <dt>Contract</dt>
          <dd>{quantity(profile.contract_demand_kva!, "kVA")}</dd>
        </div>
        <div>
          <dt>Billing floor</dt>
          <dd>{profile.demand_floor_kva ? quantity(profile.demand_floor_kva, "kVA") : "—"}</dd>
        </div>
        <div>
          <dt>Billed at</dt>
          <dd>{profile.billing_demand_kva ? quantity(profile.billing_demand_kva, "kVA") : "MISSING"}</dd>
        </div>
      </dl>
    </div>
  );
}

export function PowerFactorDial({ profile }: { profile: Profile }) {
  const pf = num(profile.power_factor);
  const lo = 0.7;
  const angle = (v: number) => Math.PI * (1 - (Math.min(1, Math.max(lo, v)) - lo) / (1 - lo));
  const point = (v: number, r: number) => [60 + r * Math.cos(angle(v)), 60 - r * Math.sin(angle(v))];
  const arc = (from: number, to: number, r: number) => {
    const [x1, y1] = point(from, r);
    const [x2, y2] = point(to, r);
    return `M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`;
  };
  const tone = pf === null ? "" : pf >= 0.95 ? "good" : pf >= 0.9 ? "warn" : "bad";
  const [nx, ny] = pf === null ? [60, 60] : point(pf, 40);
  return (
    <div className="viz">
      <div className="viz-head">
        <span className="viz-title">Power factor</span>
        <span className="viz-sub">kWh ÷ kVAh, billed on kVAh</span>
      </div>
      {pf === null ? (
        <div className="viz-empty">
          <span className="badge badge-missing">Insufficient data</span>
          <span>kWh and kVAh are both needed.</span>
        </div>
      ) : (
        <svg className="dial" viewBox="0 0 120 70" role="img" aria-label={`Power factor ${profile.power_factor}`}>
          <path d={arc(0.7, 0.9, 48)} className="dial-bad" />
          <path d={arc(0.9, 0.95, 48)} className="dial-warn" />
          <path d={arc(0.95, 1, 48)} className="dial-good" />
          <line x1="60" y1="60" x2={nx} y2={ny} className={`dial-needle tone-${tone}`} />
          <circle cx="60" cy="60" r="3.5" className="dial-hub" />
        </svg>
      )}
      {pf !== null && (
        <div className="gauge-big center">
          <span className={`tone-${tone}`}>{profile.power_factor}</span>
          <small>target 0.99</small>
        </div>
      )}
    </div>
  );
}

/** Calculated totals of the most recent runs, oldest first. MISSING stays MISSING. */
export function HistoryChart({ runs }: { runs: RunSummary[] }) {
  const recent = runs.slice(0, 14).reverse();
  const values = recent.map((r) => (r.totals.calculated ? Number(r.totals.calculated.paise) : null));
  const max = Math.max(1, ...values.map((v) => v ?? 0));
  if (recent.length === 0) return null;
  return (
    <div className="history-chart" role="img" aria-label="Total payable of recent runs">
      {recent.map((run, i) => {
        const v = values[i] ?? null;
        return (
          <a
            key={run.run_id}
            href={`#/runs/${run.run_id}`}
            className={`hbar hbar-${run.outcome}${v === null ? " hbar-missing" : ""}`}
            style={{ animationDelay: `${i * 40}ms` }}
            title={`#${run.run_id} ${run.bill_id}: ${run.totals.calculated?.inr ?? "MISSING"}`}
          >
            <span className="hbar-fill" style={{ height: v === null ? "100%" : `${Math.max(4, (v / max) * 100)}%` }} />
            <span className="hbar-label">#{run.run_id}</span>
          </a>
        );
      })}
    </div>
  );
}
