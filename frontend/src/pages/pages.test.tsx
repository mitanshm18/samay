import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../test/render";
import { Dashboard } from "./Dashboard";
import { NewBill } from "./NewBill";
import { RunView } from "./RunView";
import calculateOnly from "../test/fixtures/run-calculate-only.json";
import differing from "../test/fixtures/run-differing.json";
import missing from "../test/fixtures/run-missing-data.json";
import passThrough from "../test/fixtures/run-pass-through.json";
import runs from "../test/fixtures/runs.json";

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

async function showRun(fixture: { run: { run_id: number } }) {
  mockApi({ [`/api/runs/${fixture.run.run_id}`]: [200, fixture] });
  render(<RunView id={fixture.run.run_id} />);
  await screen.findByRole("heading", { level: 1 });
}

describe("run view", () => {
  it("shows a differing line and the total payable", async () => {
    await showRun(differing);
    expect(screen.getAllByText("Differs").length).toBeGreaterThan(0);
    expect(screen.getAllByText("₹11,26,060.00").length).toBeGreaterThan(0);
    expect(screen.getByText("Needs review")).toBeTruthy();
  });

  it("never shows a missing value as zero", async () => {
    await showRun(missing);
    expect(missing.run.totals.calculated).toBeNull();
    expect(screen.getAllByText(/MISSING/).length).toBeGreaterThan(0);
    // The total payable KPI is MISSING, not ₹0.00.
    const kpi = screen.getByText("Total payable (recalculated by SAMAY)").closest(".kpi") as HTMLElement;
    expect(within(kpi).queryByText("₹0.00")).toBeNull();
    expect(within(kpi).getByText(/MISSING/)).toBeTruthy();
  });

  it("marks pass-through lines and estimates", async () => {
    await showRun(passThrough);
    expect(screen.getAllByText("Taken as printed").length).toBeGreaterThan(1);
    expect(screen.getAllByText("Not checked").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/ESTIMATED|Estimated/).length).toBeGreaterThan(0);
  });

  it("titles the totals section by what the totals did", async () => {
    await showRun(differing); // a line differs, but the totals match
    expect(screen.getByRole("heading", { name: "Why the totals match" })).toBeTruthy();
  });

  it("says when the totals cannot be compared", async () => {
    await showRun(missing);
    expect(screen.getByRole("heading", { name: "Why the totals cannot be compared" })).toBeTruthy();
  });

  it("says when the totals differ", async () => {
    const changed = structuredClone(differing);
    Object.assign(changed.report.reconciliation.total.difference, { value: "1.00", paise: "100" });
    await showRun(changed);
    expect(screen.getByRole("heading", { name: "Why the totals differ" })).toBeTruthy();
  });

  it("labels a calculate-only run", async () => {
    await showRun(calculateOnly);
    expect(screen.getAllByText("Calculated only").length).toBeGreaterThan(0);
  });

  it("shows the synthetic tariff warning", async () => {
    await showRun(differing);
    expect(screen.getAllByText(/synthetic/i).length).toBeGreaterThan(0);
  });

  it("reports an unknown run", async () => {
    mockApi({});
    render(<RunView id={99} />);
    expect((await screen.findByRole("alert")).textContent).toContain("no mock for /api/runs/99");
  });
});

describe("dashboard", () => {
  it("lists saved runs with MISSING totals shown as MISSING", async () => {
    mockApi({ "/api/runs?limit=100": [200, runs] });
    render(<Dashboard />);
    await screen.findByText("EXAMPLE-MISSING-DATA");
    expect(screen.getByText("EXAMPLE-DIFFERING")).toBeTruthy();
    const row = screen.getByText("EXAMPLE-MISSING-DATA").closest("tr") as HTMLElement;
    expect(within(row).getAllByText("MISSING").length).toBeGreaterThan(0);
    expect(within(row).queryByText("₹0.00")).toBeNull();
  });
});

describe("check a bill", () => {
  it("lists every validation error and saves nothing", async () => {
    const fetch = mockApi({
      "/api/validate": [
        422,
        {
          format: "samay.report/1",
          command: "validate",
          exit_code: "2",
          valid: false,
          warnings: [],
          errors: [{ path: "$.bill_id", code: "missing", message: "required" }],
        },
      ],
    });
    render(<NewBill />);
    fireEvent.change(screen.getByLabelText(/Bill \(samay.bill/), { target: { value: "{}" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Validate" })));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("1 problem");
    expect(alert.textContent).toContain("$.bill_id");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("opens the saved run after reconciling", async () => {
    mockApi({
      "/api/runs?command=reconcile": [201, { run: differing.run, document_was_new: true, report: differing.report }],
    });
    render(<NewBill />);
    fireEvent.click(screen.getByRole("button", { name: "differing.json" }));
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Calculate, reconcile and save" })),
    );
    await waitFor(() => expect(window.location.hash).toBe(`#/runs/${differing.run.run_id}`));
  });
});
