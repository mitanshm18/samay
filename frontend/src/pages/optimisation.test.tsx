import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../test/render";
import { OptimisationPanel } from "./Optimisation";
import { RunView } from "./RunView";
import differing from "../test/fixtures/run-differing.json";
import gb2 from "../test/fixtures/optimisation-gb2.json";
import gb3 from "../test/fixtures/optimisation-gb3.json";

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

async function show(fixture: { run_id: number }) {
  mockApi({ [`/api/runs/${fixture.run_id}/optimisation`]: [200, fixture] });
  render(<OptimisationPanel runId={fixture.run_id} />);
  await screen.findByRole("heading", { name: "Recommendations" });
}

function card(title: string): HTMLElement {
  return screen.getByRole("heading", { name: title }).closest("article") as HTMLElement;
}

describe("cost optimisation", () => {
  it("labels every synthetic saving as illustrative, never as a real saving", async () => {
    await show(gb2);
    expect(screen.getByRole("note").textContent).toContain("illustrative");
    const excess = card("Avoid the excess demand penalty");
    expect(within(excess).getByText("₹38,981.00")).toBeTruthy();
    expect(within(excess).getByText("Illustrative saving per bill")).toBeTruthy();
    expect(within(excess).getByText(/not a real saving/)).toBeTruthy();
    expect(screen.queryByText(/Estimated saving/)).toBeNull();
  });

  it("picks the largest priced opportunity exactly", async () => {
    await show(gb2);
    const hero = screen.getByText("Largest priced opportunity").closest(".opt-hero") as HTMLElement;
    expect(within(hero).getByText("₹53,072.00")).toBeTruthy();
    expect(within(hero).getByText(/not additive/)).toBeTruthy();
  });

  it("shows Insufficient data, never ₹0, when the bill total is missing", async () => {
    await show(gb3);
    expect(gb3.current_total).toBeNull();
    const hero = screen.getByText("Largest priced opportunity").closest(".opt-hero") as HTMLElement;
    expect(within(hero).getByText("Insufficient data")).toBeTruthy();
    expect(screen.queryByText(/₹0\.00/)).toBeNull();
    // The off-peak reading is missing: the zone chart says so instead of drawing a bar.
    expect(screen.getAllByText("MISSING").length).toBeGreaterThan(0);
    const shift = card("Load shifting: insufficient data");
    expect(within(shift).getAllByText("Insufficient data").length).toBeGreaterThan(0);
  });

  it("separates actionable from indicative and filters by kind", async () => {
    await show(gb2);
    expect(screen.getAllByRole("article")).toHaveLength(gb2.recommendations.length);
    fireEvent.click(screen.getByRole("tab", { name: /^Actionable/ }));
    const shown = screen.getAllByRole("article");
    expect(shown).toHaveLength(Number(gb2.counts.actionable));
    for (const article of shown) expect(within(article).getByText("Actionable")).toBeTruthy();
  });

  it("shows the assumptions, basis and scenario behind a saving", async () => {
    await show(gb2);
    const shift = card("Shift flexible load out of peak hours");
    fireEvent.click(within(shift).getByRole("button", { name: "How this was worked out" }));
    expect(within(shift).getByText("Assumptions")).toBeTruthy();
    expect(within(shift).getByText("Calculation basis")).toBeTruthy();
    expect(within(shift).getAllByText(/Scenario:/).length).toBeGreaterThan(0);
    expect(within(shift).getAllByText(/confidence/i).length).toBeGreaterThan(0);
  });

  it("calls a saving estimated only when the API says so", async () => {
    const verified = structuredClone(gb2);
    verified.synthetic = false;
    for (const r of verified.recommendations) {
      if (r.saving.status === "illustrative") r.saving.status = "estimated";
    }
    await show(verified);
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.getAllByText("Estimated saving per bill").length).toBeGreaterThan(0);
    expect(screen.queryByText(/not a real saving/)).toBeNull();
  });

  it("reports an API error", async () => {
    mockApi({});
    render(<OptimisationPanel runId={42} />);
    expect((await screen.findByRole("alert")).textContent).toContain("no mock for /api/runs/42/optimisation");
  });

  it("is a tab of the run view", async () => {
    mockApi({
      [`/api/runs/${differing.run.run_id}`]: [200, differing],
      [`/api/runs/${differing.run.run_id}/optimisation`]: [200, { ...gb2, run_id: differing.run.run_id }],
    });
    render(<RunView id={differing.run.run_id} tab="optimisation" />);
    await screen.findByRole("heading", { name: "Recommendations" });
    expect(screen.getByRole("tab", { name: /Cost optimisation/ }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByRole("heading", { name: /Why the totals/ })).toBeNull();
  });
});
