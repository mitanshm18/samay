import { describe, expect, it } from "vitest";
import { parseRoute, runHash } from "./router";

describe("routes", () => {
  it("parses pages and run tabs", () => {
    expect(parseRoute("")).toEqual({ page: "dashboard" });
    expect(parseRoute("#/new")).toEqual({ page: "new" });
    expect(parseRoute("#/runs/12")).toEqual({ page: "run", id: 12, tab: "reconciliation" });
    expect(parseRoute("#/runs/12/optimisation")).toEqual({ page: "run", id: 12, tab: "optimisation" });
    expect(parseRoute("#/runs/12/calculation")).toEqual({ page: "run", id: 12, tab: "calculation" });
    expect(parseRoute("#/runs/12/other")).toEqual({ page: "dashboard" });
    expect(parseRoute("#/runs/0")).toEqual({ page: "dashboard" });
  });

  it("builds run links", () => {
    expect(runHash(5)).toBe("#/runs/5");
    expect(runHash(5, "optimisation")).toBe("#/runs/5/optimisation");
  });
});
