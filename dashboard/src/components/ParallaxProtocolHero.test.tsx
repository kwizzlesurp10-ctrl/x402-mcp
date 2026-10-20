/**
 * @vitest-environment jsdom
 */
import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ParallaxProtocolHero } from "./ParallaxProtocolHero";

describe("ParallaxProtocolHero", () => {
  it("does not claim the Linux Foundation certifies this node", () => {
    const { container } = render(<ParallaxProtocolHero telemetry={null} />);
    const text = container.textContent ?? "";

    expect(text).toMatch(/Linux Foundation/i);
    expect(text).toMatch(/protocol layer/i);
    expect(text).toMatch(/not certified/i);
    expect(text).not.toMatch(/governed by the Linux Foundation/i);
  });
});
