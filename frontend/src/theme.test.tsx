import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import { THEME_KEY, applyTheme, readPref, resolveTheme, useTheme } from "./theme";

function prefersLight(light: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: light && query.includes("light"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

function Harness() {
  const { pref, theme, setPref } = useTheme();
  return (
    <>
      <span data-testid="theme">{theme}</span>
      <ThemeSwitcher pref={pref} onChange={setPref} />
    </>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  prefersLight(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.theme;
});

describe("theme", () => {
  it("defaults to the system setting", () => {
    expect(readPref()).toBe("system");
    expect(resolveTheme("system")).toBe("dark");
    prefersLight(true);
    expect(resolveTheme("system")).toBe("light");
  });

  it("ignores an unknown saved value", () => {
    window.localStorage.setItem(THEME_KEY, "purple");
    expect(readPref()).toBe("system");
  });

  it("applies the theme to the page root", () => {
    expect(applyTheme("light")).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.dataset.themePref).toBe("light");
  });

  it("saves the choice so it survives a reload", () => {
    const first = render(<Harness />);
    act(() => fireEvent.click(screen.getByRole("radio", { name: /Light/ })));
    expect(window.localStorage.getItem(THEME_KEY)).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    first.unmount();
    delete document.documentElement.dataset.theme;
    render(<Harness />); // a fresh page load reads the saved choice
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(screen.getByRole("radio", { name: /Light/ }).getAttribute("aria-checked")).toBe("true");
  });

  it("is a keyboard radio group", () => {
    render(<Harness />);
    const system = screen.getByRole("radio", { name: /System/ });
    expect(system.getAttribute("aria-checked")).toBe("true");
    expect(system.tabIndex).toBe(0);
    act(() => fireEvent.keyDown(system, { key: "ArrowRight" }));
    expect(window.localStorage.getItem(THEME_KEY)).toBe("light");
    act(() => fireEvent.keyDown(screen.getByRole("radio", { name: /Light/ }), { key: "ArrowRight" }));
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("still works when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readPref()).toBe("system");
    render(<Harness />);
    act(() => fireEvent.click(screen.getByRole("radio", { name: /Dark/ })));
    expect(document.documentElement.dataset.theme).toBe("dark");
    vi.restoreAllMocks();
  });
});
