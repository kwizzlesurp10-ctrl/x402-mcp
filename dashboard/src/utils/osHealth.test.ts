import { describe, expect, it } from "vitest";
import { formatUptime, LEVEL_COLOR, metricLevel } from "./osHealth";

describe("metricLevel", () => {
  it("mirrors server thresholds per metric", () => {
    expect(metricLevel("cpu", 10)).toBe("ok");
    expect(metricLevel("cpu", 75)).toBe("warn");
    expect(metricLevel("cpu", 90)).toBe("critical");
    expect(metricLevel("memory", 79.9)).toBe("ok");
    expect(metricLevel("memory", 86.4)).toBe("warn");
    expect(metricLevel("memory", 92)).toBe("critical");
    expect(metricLevel("disk", 84.9)).toBe("ok");
    expect(metricLevel("disk", 88.9)).toBe("warn");
    expect(metricLevel("disk", 95.1)).toBe("critical");
  });

  it("has a color for every level", () => {
    expect(LEVEL_COLOR.ok).toBeTruthy();
    expect(LEVEL_COLOR.warn).toBeTruthy();
    expect(LEVEL_COLOR.critical).toBeTruthy();
  });
});

describe("formatUptime", () => {
  it("formats minutes, hours, and days", () => {
    expect(formatUptime(59)).toBe("0m");
    expect(formatUptime(45 * 60)).toBe("45m");
    expect(formatUptime(3 * 3600 + 20 * 60)).toBe("3h 20m");
    expect(formatUptime(2 * 86400 + 5 * 3600)).toBe("2d 5h");
  });

  it("handles invalid input", () => {
    expect(formatUptime(-1)).toBe("—");
    expect(formatUptime(Number.NaN)).toBe("—");
  });
});
