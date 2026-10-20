import { describe, expect, it } from "vitest";
import { refreshErrors, settledSlice } from "./refreshLoad";

describe("settledSlice", () => {
  it("unwraps a fulfilled result", () => {
    expect(settledSlice({ status: "fulfilled", value: 7 })).toEqual({ ok: true, value: 7 });
  });

  it("stringifies a rejected Error", () => {
    expect(settledSlice({ status: "rejected", reason: new Error("/stats failed: 500") })).toEqual({
      ok: false,
      error: "/stats failed: 500",
    });
  });
});

describe("refreshErrors", () => {
  it("returns null when every slice succeeded", () => {
    expect(refreshErrors([{ ok: true, value: 1 }, { ok: true, value: 2 }])).toBeNull();
  });

  it("joins failures so one dead endpoint cannot hide the rest", () => {
    expect(
      refreshErrors([
        { ok: false, error: "/stats failed: 500" },
        { ok: true, value: [{ ts: "1" }] },
      ]),
    ).toBe("/stats failed: 500");
  });
});
