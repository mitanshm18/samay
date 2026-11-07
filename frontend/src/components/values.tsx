import type { ReactNode } from "react";
import type { LineStatus, Traced } from "../api";
import { inrFromDecimal, inrFromPaise, quantity, signedTone } from "../format";

export function Badge({
  tone,
  children,
  title,
}: {
  tone: "missing" | "estimated" | "passthrough" | "synthetic" | "neutral" | "good" | "bad" | "info";
  children: ReactNode;
  title?: string;
}) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

/** Shown wherever a value is MISSING: never a zero, always with the reasons. */
export function Missing({ value, label = "MISSING" }: { value: Traced; label?: string }) {
  const reasons = value.missing_reasons?.length ? value.missing_reasons : [value.note];
  return (
    <span className="missing">
      <Badge tone="missing" title={reasons.join("\n")}>
        {label}
      </Badge>
      <span className="reason">{reasons.join("; ")}</span>
    </span>
  );
}

export function EstimateNote({ bases }: { bases: string[] }) {
  if (!bases.length) return null;
  return (
    <span className="estimate">
      <Badge tone="estimated" title={bases.join("\n")}>
        ESTIMATED
      </Badge>
      <span className="reason">{bases.join("; ")}</span>
    </span>
  );
}

function moneyText(value: Traced): string {
  if (value.paise !== undefined) return inrFromPaise(value.paise);
  if (value.value !== null && value.unit?.startsWith("INR")) return inrFromDecimal(value.value);
  return value.value === null ? "" : quantity(value.value, value.unit);
}

/** A money amount from a report. `absent` is what to show when the line was not printed. */
export function Amount({
  value,
  absent = "Not on bill",
  missingLabel = "MISSING",
  signed = false,
  showEstimate = true,
}: {
  value: Traced | undefined | null;
  absent?: string;
  missingLabel?: string;
  signed?: boolean;
  showEstimate?: boolean;
}) {
  if (!value) return <span className="muted">{absent}</span>;
  if (value.value === null) return <Missing value={value} label={missingLabel} />;
  const tone = signed && value.paise !== undefined ? signedTone(value.paise) : undefined;
  return (
    <span className="amount-cell">
      <span className={`amount${tone ? ` amount-${tone}` : ""}`} title={value.note}>
        {signed && tone === "positive" ? "+" : ""}
        {moneyText(value)}
      </span>
      {showEstimate && value.rests_on_estimate ? (
        <EstimateNote bases={value.estimate_bases} />
      ) : null}
    </span>
  );
}

export function QuantityValue({ value }: { value: Traced }) {
  if (value.value === null) return <Missing value={value} />;
  return <span className="amount">{quantity(value.value, value.unit)}</span>;
}

export const STATUS: Record<LineStatus, { label: string; tone: Parameters<typeof Badge>[0]["tone"]; help: string }> = {
  MATCH: { label: "Match", tone: "good", help: "Printed and recalculated amounts are equal, to the paisa." },
  DIFFERS: { label: "Differs", tone: "bad", help: "Printed and recalculated amounts differ." },
  CALCULATED_ONLY: {
    label: "Not on bill",
    tone: "info",
    help: "SAMAY calculated this line, but it is not on the printed bill.",
  },
  CANNOT_COMPARE: {
    label: "Cannot compare",
    tone: "missing",
    help: "The line is printed, but the printed or the calculated amount is missing.",
  },
  NOT_RECALCULATED: {
    label: "Taken as printed",
    tone: "passthrough",
    help: "Pass-through line: included as printed, not recalculated or checked.",
  },
};

export function StatusPill({ status }: { status: LineStatus }) {
  const info = STATUS[status];
  return (
    <Badge tone={info.tone} title={info.help}>
      {info.label}
    </Badge>
  );
}

export function OutcomePill({ outcome }: { outcome: "clean" | "not-clean" | "calculated" }) {
  if (outcome === "clean") return <Badge tone="good">Clean</Badge>;
  if (outcome === "not-clean") return <Badge tone="bad">Needs review</Badge>;
  return <Badge tone="neutral">Calculated only</Badge>;
}
