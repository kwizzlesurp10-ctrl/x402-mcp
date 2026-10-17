/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Bubble } from "./Bubble";

describe("Bubble Canvas UI Component", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders children cleanly inside container", () => {
    render(
      <Bubble>
        <div data-testid="test-child">Mission Control Content</div>
      </Bubble>
    );

    expect(screen.getByTestId("test-child")).toBeDefined();
    expect(screen.getByText("Mission Control Content")).toBeDefined();
  });

  it("renders canvas element with subdued zIndex of 15", () => {
    const { container } = render(
      <Bubble>
        <div>Content</div>
      </Bubble>
    );

    const canvas = container.querySelector("canvas");
    expect(canvas).toBeDefined();
    expect(canvas?.style.zIndex).toBe("15");
    expect(canvas?.style.pointerEvents).toBe("none");
  });

  it("handles trail=0 and ambient=true safely without crashing", () => {
    const { container: c1 } = render(
      <Bubble trail={0}>
        <div>No trail</div>
      </Bubble>
    );
    expect(c1.querySelector("canvas")).toBeDefined();

    const { container: c2 } = render(
      <Bubble ambient={true}>
        <div>Ambient mode</div>
      </Bubble>
    );
    expect(c2.querySelector("canvas")).toBeDefined();
  });

  it("cleans up event listeners on unmount", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      arc: vi.fn(),
      createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
      fill: vi.fn(),
      stroke: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
    } as unknown as CanvasRenderingContext2D);

    const removeListenerSpy = vi.spyOn(window, "removeEventListener");
    const docRemoveListenerSpy = vi.spyOn(document, "removeEventListener");

    const { unmount } = render(
      <Bubble trail={2}>
        <div>Testing listeners</div>
      </Bubble>
    );

    unmount();

    expect(removeListenerSpy).toHaveBeenCalledWith("resize", expect.any(Function));
    expect(removeListenerSpy).toHaveBeenCalledWith("mousemove", expect.any(Function));
    expect(docRemoveListenerSpy).toHaveBeenCalledWith("mouseleave", expect.any(Function));
  });

  it("handles mousemove and mouseleave without throwing in jsdom", () => {
    render(
      <Bubble size={8} trail={2}>
        <div>Interactive canvas</div>
      </Bubble>
    );

    expect(() => {
      fireEvent.mouseMove(window, { clientX: 200, clientY: 300 });
      fireEvent(document, new Event("mouseleave"));
    }).not.toThrow();
  });
});
