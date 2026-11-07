// The SAMAY API (docs/api.md), through the dev-server proxy at /api. Every response is
// checked against these schemas: money must arrive as strings, never JSON numbers, and
// a missing value as null. Anything else is shown as an error, not guessed at.

import { z } from "zod";

const Money = z.object({ paise: z.string(), inr: z.string() }).nullable();

export const Traced = z
  .object({
    value: z.string().nullable(),
    unit: z.string().optional(),
    paise: z.string().optional(),
    provenance: z.string(),
    status: z.string(),
    note: z.string(),
    missing_reasons: z.array(z.string()).optional(),
    rests_on_estimate: z.boolean(),
    estimate_bases: z.array(z.string()),
  })
  .passthrough();
export type Traced = z.infer<typeof Traced>;

const Assumption = z.object({ key: z.string(), text: z.string() });
const Issue = z.object({ severity: z.string(), code: z.string(), message: z.string() });
const InputError = z.object({ path: z.string(), code: z.string(), message: z.string() });

const Quantity = Traced.extend({ key: z.string(), label: z.string(), formula: z.string() });
export type Quantity = z.infer<typeof Quantity>;

const MoneyLine = z.object({
  code: z.string(),
  label: z.string(),
  basis: z.string(),
  formula: z.string(),
  rounding: z.string().nullable(),
  exact: Traced.nullable(),
  amount: Traced,
  assumptions: z.array(Assumption),
});
export type MoneyLine = z.infer<typeof MoneyLine>;

export const LineStatus = z.enum([
  "MATCH",
  "DIFFERS",
  "CALCULATED_ONLY",
  "CANNOT_COMPARE",
  "NOT_RECALCULATED",
]);
export type LineStatus = z.infer<typeof LineStatus>;

const Comparison = z.object({
  code: z.string(),
  label: z.string(),
  status: LineStatus,
  on_printed_bill: z.boolean(),
  printed: Traced.optional(),
  calculated: Traced.optional(),
  difference: Traced,
  rests_on_estimate: z.boolean(),
  estimate_bases: z.array(z.string()),
});
export type Comparison = z.infer<typeof Comparison>;

const Calculation = z.object({
  bill_id: z.string(),
  complete: z.boolean(),
  quantities: z.array(Quantity),
  lines: z.array(MoneyLine),
  subtotal: Traced,
  total: Traced,
  taken_as_printed: z.object({ line_count: z.string(), total: Traced }),
  rests_on_estimate: z.boolean(),
  estimate_bases: z.array(z.string()),
  assumptions: z.array(Assumption),
});
export type Calculation = z.infer<typeof Calculation>;

const Reconciliation = z.object({
  lines: z.array(Comparison),
  total: z.object({
    printed_total_given: z.boolean(),
    printed: Traced.optional(),
    calculated: Traced,
    difference: Traced,
    printed_lines_residual: Traced,
  }),
  explanation: z.object({
    state: z.enum(["COMPLETE", "PARTIAL", "UNDETERMINABLE"]),
    compared_line_count: z.string(),
    compared_difference: Traced,
    not_compared: z.array(
      z.object({ code: z.string(), label: z.string(), status: LineStatus, reason: z.string() }),
    ),
  }),
  counts: z.record(z.string()),
  taken_as_printed_total: Traced,
  clean: z.boolean(),
  rests_on_estimate: z.boolean(),
});
export type Reconciliation = z.infer<typeof Reconciliation>;

export const Report = z.object({
  format: z.literal("samay.report/1"),
  command: z.enum(["calculate", "reconcile"]),
  exit_code: z.string(),
  tariff: z.object({ id: z.string(), name: z.string(), status: z.string() }),
  synthetic: z.boolean(),
  banner: z.string().nullable(),
  warnings: z.array(Issue),
  errors: z.array(InputError),
  calculation: Calculation,
  reconciliation: Reconciliation.optional(),
});
export type Report = z.infer<typeof Report>;

export const RunSummary = z.object({
  run_id: z.number().int(),
  bill_id: z.string(),
  command: z.enum(["calculate", "reconcile"]),
  exit_code: z.number().int(),
  outcome: z.enum(["clean", "not-clean", "calculated"]),
  outcome_text: z.string(),
  tariff: z.object({ id: z.string(), status: z.string() }),
  synthetic: z.boolean(),
  totals: z.object({ calculated: Money, printed: Money, difference: Money }),
  explanation: z.string().nullable(),
  created_at: z.string(),
});
export type RunSummary = z.infer<typeof RunSummary>;

const RunList = z.object({ runs: z.array(RunSummary) });
const Created = z.object({ run: RunSummary, document_was_new: z.boolean(), report: Report });
export type Created = z.infer<typeof Created>;
const RunDetail = z.object({
  run: RunSummary,
  engine_version: z.string(),
  source_sha256: z.string(),
  report_sha256: z.string(),
  report: Report,
});
export type RunDetail = z.infer<typeof RunDetail>;
const Verify = z.object({
  run_id: z.number().int(),
  matches: z.boolean(),
  stored_sha256: z.string(),
  recomputed_sha256: z.string(),
  message: z.string(),
});
export type Verify = z.infer<typeof Verify>;
const Validation = z.object({
  valid: z.boolean(),
  exit_code: z.string(),
  banner: z.string().nullable().optional(),
  tariff: z.object({ id: z.string(), name: z.string(), status: z.string() }).optional(),
  warnings: z.array(Issue),
  errors: z.array(InputError),
});
export type Validation = z.infer<typeof Validation>;
const Health = z.object({ status: z.string(), version: z.string(), database: z.string() });
export type Health = z.infer<typeof Health>;
const Problem = z.object({ error: z.string(), message: z.string() });

/** An API call that did not succeed, with a message a person can act on. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly validation?: Validation,
  ) {
    super(message);
  }
}

async function call<T>(schema: z.ZodType<T>, path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError("Cannot reach the SAMAY API. Start it with: make api", 0);
  }
  const text = await response.text();
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw new ApiError(
      response.status >= 500 || response.status === 0
        ? "Cannot reach the SAMAY API. Start it with: make api"
        : `Unexpected answer from the API (HTTP ${response.status})`,
      response.status,
    );
  }
  if (!response.ok) {
    if (response.status === 422) {
      const validation = Validation.safeParse(body);
      if (validation.success) {
        throw new ApiError("The bill is not valid.", 422, validation.data);
      }
      throw new ApiError("The request was not accepted (HTTP 422).", 422);
    }
    const problem = Problem.safeParse(body);
    throw new ApiError(
      problem.success ? problem.data.message : `The API answered HTTP ${response.status}`,
      response.status,
    );
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError("The API answer did not have the expected shape.", response.status);
  }
  return parsed.data;
}

const json = { "content-type": "application/json" };

export const api = {
  health: () => call(Health, "/api/health"),
  validate: (bill: string) =>
    call(Validation, "/api/validate", { method: "POST", headers: json, body: bill }),
  save: (bill: string, command: "reconcile" | "calculate") =>
    call(Created, `/api/runs?command=${command}`, { method: "POST", headers: json, body: bill }),
  runs: (limit = 100) => call(RunList, `/api/runs?limit=${limit}`).then((r) => r.runs),
  run: (id: number) => call(RunDetail, `/api/runs/${id}`),
  verify: (id: number) => call(Verify, `/api/runs/${id}/verify`, { method: "POST" }),
  reportUrl: (id: number) => `/api/runs/${id}/report`,
  sourceUrl: (id: number) => `/api/runs/${id}/source`,
};
