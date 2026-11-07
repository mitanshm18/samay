import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";
import differing from "./test/fixtures/run-differing.json";

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(typeof body === "string" ? body : JSON.stringify(body), { status }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("posts the bill text unchanged and parses the saved run", async () => {
    const fetch = respond(201, { run: differing.run, document_was_new: true, report: differing.report });
    vi.stubGlobal("fetch", fetch);
    const created = await api.save('{"format": "samay.bill/1"}', "reconcile");
    expect(created.run.run_id).toBe(differing.run.run_id);
    expect(fetch).toHaveBeenCalledWith("/api/runs?command=reconcile", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: '{"format": "samay.bill/1"}',
    });
  });

  it("refuses money sent as a JSON number", async () => {
    const run = { ...differing.run, totals: { ...differing.run.totals, calculated: { paise: 112606000, inr: "x" } } };
    vi.stubGlobal("fetch", respond(200, { runs: [run] }));
    await expect(api.runs()).rejects.toThrow("expected shape");
  });

  it("returns every validation error on 422", async () => {
    const body = {
      format: "samay.report/1",
      command: "validate",
      exit_code: "2",
      valid: false,
      warnings: [],
      errors: [
        { path: "$.bill_id", code: "missing", message: "required" },
        { path: "$.period", code: "missing", message: "required" },
      ],
    };
    vi.stubGlobal("fetch", respond(422, body));
    const error = await api.validate("{}").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).validation?.errors).toHaveLength(2);
  });

  it("explains a stopped database (503)", async () => {
    vi.stubGlobal(
      "fetch",
      respond(503, { error: "database-unavailable", message: "Cannot reach SAMAY's database. Start it with: make db-up" }),
    );
    await expect(api.runs()).rejects.toThrow("make db-up");
  });

  it("explains a stopped API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.health()).rejects.toThrow("make api");
    vi.stubGlobal("fetch", respond(502, "Bad gateway"));
    await expect(api.health()).rejects.toThrow("make api");
  });

  it("reports 404 with the API's message", async () => {
    vi.stubGlobal("fetch", respond(404, { error: "run-not-found", message: "no saved run with id 9" }));
    await expect(api.run(9)).rejects.toThrow("no saved run with id 9");
  });
});
