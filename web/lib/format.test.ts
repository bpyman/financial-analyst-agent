import { describe, expect, it } from "vitest";
import { axisTick, parseLink } from "./format";

describe("axisTick", () => {
  it("compacts dollars by scale", () => {
    expect(axisTick(0, "usd")).toBe("$0");
    expect(axisTick(8e9, "usd")).toBe("$8B");
    expect(axisTick(12.5e9, "usd")).toBe("$12.5B");
    expect(axisTick(1.25e12, "usd")).toBe("$1.25T");
    expect(axisTick(300e6, "usd")).toBe("$300M");
    expect(axisTick(-2e9, "usd")).toBe("-$2B");
    expect(axisTick(82_886_000_000, "usd")).toBe("$82.9B");
  });

  it("shows ratios as percent, keeping a decimal only when a tick needs it", () => {
    expect(axisTick(0.4, "percent")).toBe("40%");
    expect(axisTick(0.425, "percent")).toBe("42.5%");
    expect(axisTick(-0.05, "percent")).toBe("-5%");
    expect(axisTick(0.253, "percent")).toBe("25.3%");
  });

  it("shows multiples with one decimal", () => {
    expect(axisTick(12, "multiple")).toBe("12.0x");
    expect(axisTick(12.34, "multiple")).toBe("12.3x");
  });

  it("draws nothing for a non-number", () => {
    expect(axisTick(Number.NaN, "usd")).toBe("");
  });
});

describe("parseLink", () => {
  it("accepts http(s) markdown links only", () => {
    expect(parseLink("[sec.gov](https://www.sec.gov/x.htm)")).toEqual({
      text: "sec.gov",
      href: "https://www.sec.gov/x.htm",
    });
    expect(parseLink("[x](javascript:alert(1))")).toBeNull();
    expect(parseLink("plain text")).toBeNull();
  });
});
