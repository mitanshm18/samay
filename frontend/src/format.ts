// Display formatting only. Every amount arrives from the API as a string (paise, or an
// exact decimal in rupees) and is regrouped as text: no number parsing, no arithmetic,
// no rounding. A missing value is never turned into zero here.

const PAISE = /^-?(0|[1-9][0-9]*)$/;
const DECIMAL = /^-?[0-9]+(\.[0-9]+)?$/;

/** Indian digit grouping of a whole-number string: 1234567 -> 12,34,567. */
export function groupIndian(whole: string): string {
  if (!/^[0-9]+$/.test(whole)) throw new Error(`not a whole number: ${whole}`);
  if (whole.length <= 3) return whole;
  const tail = whole.slice(-3);
  let head = whole.slice(0, -3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head) groups.unshift(head);
  return [...groups, tail].join(",");
}

/** "112606000" (paise) -> "₹11,26,060.00". Same output as SAMAY's Money.format_inr. */
export function inrFromPaise(paise: string): string {
  if (!PAISE.test(paise)) throw new Error(`not a paise amount: ${paise}`);
  const negative = paise.startsWith("-");
  const digits = (negative ? paise.slice(1) : paise).padStart(3, "0");
  const whole = digits.slice(0, -2).replace(/^0+(?=[0-9])/, "");
  return `${negative ? "-" : ""}₹${groupIndian(whole)}.${digits.slice(-2)}`;
}

/** An exact decimal amount in rupees, shown with every digit it has: "164938.00000". */
export function inrFromDecimal(value: string): string {
  if (!DECIMAL.test(value)) throw new Error(`not a decimal amount: ${value}`);
  const negative = value.startsWith("-");
  const [whole = "0", fraction = ""] = (negative ? value.slice(1) : value).split(".");
  const shown = fraction.replace(/0+$/, "").padEnd(2, "0");
  return `${negative ? "-" : ""}₹${groupIndian(whole)}.${shown}`;
}

/** A quantity such as "412.345" kVA, grouped but otherwise unchanged. */
export function quantity(value: string, unit?: string): string {
  let text = value;
  if (DECIMAL.test(value)) {
    const negative = value.startsWith("-");
    const [whole = "0", fraction] = (negative ? value.slice(1) : value).split(".");
    text = `${negative ? "-" : ""}${groupIndian(whole)}${fraction !== undefined ? `.${fraction}` : ""}`;
  }
  return unit ? `${text} ${unit}` : text;
}

export function signedTone(paise: string): "zero" | "positive" | "negative" {
  if (!PAISE.test(paise)) throw new Error(`not a paise amount: ${paise}`);
  if (paise === "0") return "zero";
  return paise.startsWith("-") ? "negative" : "positive";
}

export function dateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function words(code: string): string {
  const text = code.replace(/[_-]+/g, " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}
