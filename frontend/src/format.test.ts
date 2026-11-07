import { describe, expect, it } from "vitest";
import { groupIndian, inrFromDecimal, inrFromPaise, quantity, largestPaise, signedTone } from "./format";

describe("money formatting (text only, no arithmetic)", () => {
  it.each([
    ["0", "₹0.00"],
    ["1", "₹0.01"],
    ["10", "₹0.10"],
    ["100", "₹1.00"],
    ["-1", "-₹0.01"],
    ["16493800", "₹1,64,938.00"],
    ["112606000", "₹11,26,060.00"],
    ["-112606000", "-₹11,26,060.00"],
    ["90000000001", "₹90,00,00,000.01"],
    // 2^53 + 1: still exact, because nothing is parsed as a number.
    ["9007199254740993", "₹9,00,71,99,25,47,409.93"],
  ])("paise %s -> %s (same as Money.format_inr)", (paise, text) => {
    expect(inrFromPaise(paise)).toBe(text);
  });

  it.each(["", "1.5", "01", "-0x1", "1e3", " 1", "NaN"])("refuses %j", (bad) => {
    expect(() => inrFromPaise(bad)).toThrow();
  });

  it("keeps every digit of an exact amount", () => {
    expect(inrFromDecimal("164938.00000")).toBe("₹1,64,938.00");
    expect(inrFromDecimal("90451.107")).toBe("₹90,451.107");
    expect(inrFromDecimal("-0.5")).toBe("-₹0.50");
    expect(() => inrFromDecimal("1,000")).toThrow();
  });

  it("groups Indian style", () => {
    expect(groupIndian("999")).toBe("999");
    expect(groupIndian("1000")).toBe("1,000");
    expect(groupIndian("100000")).toBe("1,00,000");
    expect(groupIndian("10000000")).toBe("1,00,00,000");
    expect(() => groupIndian("-1")).toThrow();
  });

  it("formats quantities without changing them", () => {
    expect(quantity("100000.000", "kVAh")).toBe("1,00,000.000 kVAh");
    expect(quantity("0")).toBe("0");
    expect(quantity("9/10", "ratio (exact)")).toBe("9/10 ratio (exact)");
  });

  it("tells the sign from the text", () => {
    expect(signedTone("0")).toBe("zero");
    expect(signedTone("5")).toBe("positive");
    expect(signedTone("-5")).toBe("negative");
  });
});

describe("largest paise", () => {
  it("compares exactly, beyond floating point", () => {
    expect(largestPaise([])).toBeNull();
    expect(largestPaise(["100", "99", "-5"])).toBe("100");
    expect(largestPaise(["9007199254740993", "9007199254740992"])).toBe("9007199254740993");
  });
});
