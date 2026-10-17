/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Bubble } from "./Bubble";

describe("Bubble Canvas UI Adversarial Challenge", () => {
  let mockCtx: any;
  let rafCallbacks: Map<number, FrameRequestCallback>;
  let rafIdCounter: number;

  beforeEach(() => {
    rafCallbacks = new Map();
    rafIdCounter = 0;

    mockCtx = {
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      arc: vi.fn(),
      createRadialGradient: vi.fn(() => ({
        addColorStop: vi.fn(),
      })),
      fill: vi.fn(),
      stroke: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
    };

    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      mockCtx as unknown as CanvasRenderingContext2D
    );

    // Mock requestAnimationFrame and cancelAnimationFrame to accurately track frame scheduling
    vi.stubGlobal("requestAnimationFrame", vi.fn((cb: FrameRequestCallback) => {
      const id = ++rafIdCounter;
      rafCallbacks.set(id, cb);
      return id;
    }));

    vi.stubGlobal("cancelAnimationFrame", vi.fn((id: number) => {
      rafCallbacks.delete(id);
    }));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const triggerNextFrame = (time = performance.now()) => {
    const callbacks = Array.from(rafCallbacks.entries());
    rafCallbacks.clear();
    callbacks.forEach(([_, cb]) => cb(time));
  };

  describe("Prop Boundary Challenges (trail={0}, {1}, {2}, ambient={true})", () => {
    it("trail={0} completely bypasses animation and listener registration", () => {
      const addWindowListenerSpy = vi.spyOn(window, "addEventListener");
      const addDocListenerSpy = vi.spyOn(document, "addEventListener");

      const { container } = render(
        <Bubble trail={0}>
          <div data-testid="content">Child</div>
        </Bubble>
      );

      // Canvas element still exists in DOM for consistent tree shape
      expect(container.querySelector("canvas")).toBeDefined();

      // No listeners should have been added because trail <= 0 returns early
      expect(addWindowListenerSpy).not.toHaveBeenCalledWith("mousemove", expect.any(Function), expect.any(Object));
      expect(addWindowListenerSpy).not.toHaveBeenCalledWith("resize", expect.any(Function));
      expect(addDocListenerSpy).not.toHaveBeenCalledWith("mouseleave", expect.any(Function));

      // No RAF should be requested
      expect(global.requestAnimationFrame).not.toHaveBeenCalled();
    });

    it("ambient={true} completely disables trail canvas listeners and animation", () => {
      const addWindowListenerSpy = vi.spyOn(window, "addEventListener");
      const addDocListenerSpy = vi.spyOn(document, "addEventListener");

      render(
        <Bubble ambient={true}>
          <div data-testid="content">Child</div>
        </Bubble>
      );

      expect(addWindowListenerSpy).not.toHaveBeenCalledWith("mousemove", expect.any(Function), expect.any(Object));
      expect(addWindowListenerSpy).not.toHaveBeenCalledWith("resize", expect.any(Function));
      expect(addDocListenerSpy).not.toHaveBeenCalledWith("mouseleave", expect.any(Function));
      expect(global.requestAnimationFrame).not.toHaveBeenCalled();
    });

    it("trail={1} initializes single droplet and renders on mouse movement", () => {
      render(
        <Bubble trail={1}>
          <div>Child</div>
        </Bubble>
      );

      // Move mouse to trigger animation start
      fireEvent.mouseMove(window, { clientX: 100, clientY: 100 });
      expect(global.requestAnimationFrame).toHaveBeenCalledTimes(1);

      // Advance one animation frame
      triggerNextFrame();

      // One arc for trail=1
      expect(mockCtx.arc).toHaveBeenCalledTimes(1);
    });

    it("trail={2} initializes two droplets and renders on mouse movement", () => {
      render(
        <Bubble trail={2}>
          <div>Child</div>
        </Bubble>
      );

      fireEvent.mouseMove(window, { clientX: 150, clientY: 150 });
      expect(global.requestAnimationFrame).toHaveBeenCalledTimes(1);

      triggerNextFrame();

      // Two arcs for trail=2
      expect(mockCtx.arc).toHaveBeenCalledTimes(2);
    });
  });

  describe("Stationary Cursor & RAF Halting (Zero CPU/GPU looping)", () => {
    it("halts RAF loop when mouse remains stationary after 350ms idle threshold", () => {
      const realDateNow = Date.now;
      let mockTime = 1000000;
      vi.spyOn(Date, "now").mockImplementation(() => mockTime);

      render(
        <Bubble trail={2}>
          <div>Child</div>
        </Bubble>
      );

      // 1. User moves mouse -> starts animation
      fireEvent.mouseMove(window, { clientX: 200, clientY: 200 });
      expect(rafCallbacks.size).toBe(1);

      // Render a few frames while active (idleTime = 0)
      triggerNextFrame();
      expect(rafCallbacks.size).toBe(1);
      triggerNextFrame();
      expect(rafCallbacks.size).toBe(1);

      // 2. Cursor becomes stationary: advance time past 350ms idle threshold
      mockTime += 400; // Now idleTime is 400ms (> 350ms)

      // The loop should fade alpha down by 0.04 per frame
      // Simulate subsequent frames until alpha <= 0.005
      let frameCount = 0;
      while (rafCallbacks.size > 0 && frameCount < 100) {
        frameCount++;
        mockTime += 16; // ~60fps step
        triggerNextFrame();
      }

      // RAF loop MUST halt: rafCallbacks should now be empty (animId = null)
      expect(rafCallbacks.size).toBe(0);
      expect(frameCount).toBeLessThan(40); // Faded out within ~25-30 frames

      // 3. Verify stationary cursor does not loop RAF anymore
      const currentRafCalls = (global.requestAnimationFrame as any).mock.calls.length;
      // Advance time further while stationary
      mockTime += 1000;
      // No new RAF calls should have been made
      expect((global.requestAnimationFrame as any).mock.calls.length).toBe(currentRafCalls);

      // 4. Moving the mouse again wakes the loop cleanly without duplicate scheduling
      fireEvent.mouseMove(window, { clientX: 250, clientY: 250 });
      expect(rafCallbacks.size).toBe(1);
      expect((global.requestAnimationFrame as any).mock.calls.length).toBe(currentRafCalls + 1);

      Date.now = realDateNow;
    });

    it("halts RAF loop when mouse leaves window (mouseleave)", () => {
      const realDateNow = Date.now;
      let mockTime = 1000000;
      vi.spyOn(Date, "now").mockImplementation(() => mockTime);

      render(
        <Bubble trail={2}>
          <div>Child</div>
        </Bubble>
      );

      // Move mouse in
      fireEvent.mouseMove(window, { clientX: 100, clientY: 100 });
      expect(rafCallbacks.size).toBe(1);
      triggerNextFrame();

      // Mouse leaves window
      fireEvent(document, new Event("mouseleave"));

      // Run frames until alpha decays
      let frameCount = 0;
      while (rafCallbacks.size > 0 && frameCount < 100) {
        frameCount++;
        mockTime += 16;
        triggerNextFrame();
      }

      // Halts!
      expect(rafCallbacks.size).toBe(0);

      Date.now = realDateNow;
    });
  });

  describe("Canvas zIndex & Event Pass-Through / Occlusion", () => {
    it("canvas has zIndex: 15 and pointerEvents: none", () => {
      const { container } = render(
        <Bubble>
          <div>Child</div>
        </Bubble>
      );

      const canvas = container.querySelector("canvas")!;
      expect(canvas.style.zIndex).toBe("15");
      expect(canvas.style.pointerEvents).toBe("none");
      expect(canvas.style.position).toBe("fixed");
      expect(canvas.style.inset).toBe("0px");
    });

    it("permits clicking underlying buttons and reading table events without occlusion", () => {
      const buttonClickSpy = vi.fn();
      const tableRowClickSpy = vi.fn();

      render(
        <Bubble>
          <div>
            <button data-testid="test-btn" onClick={buttonClickSpy}>
              Execute Diligence
            </button>
            <table>
              <tbody>
                <tr data-testid="test-row" onClick={tableRowClickSpy}>
                  <td>1700 Penn Ave N</td>
                  <td>$0.85</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Bubble>
      );

      const button = screen.getByTestId("test-btn");
      fireEvent.click(button);
      expect(buttonClickSpy).toHaveBeenCalledTimes(1);

      const row = screen.getByTestId("test-row");
      fireEvent.click(row);
      expect(tableRowClickSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe("Event Listener Cleanup & Memory Leaks", () => {
    it("properly unregisters all window and document listeners on unmount", () => {
      const removeWindowSpy = vi.spyOn(window, "removeEventListener");
      const removeDocSpy = vi.spyOn(document, "removeEventListener");

      const { unmount } = render(
        <Bubble trail={2}>
          <div>Child</div>
        </Bubble>
      );

      // Start animation so an animId exists
      fireEvent.mouseMove(window, { clientX: 50, clientY: 50 });
      expect(rafCallbacks.size).toBe(1);

      unmount();

      // Verify removeEventListener called for all registered listeners
      expect(removeWindowSpy).toHaveBeenCalledWith("resize", expect.any(Function));
      expect(removeWindowSpy).toHaveBeenCalledWith("mousemove", expect.any(Function));
      expect(removeDocSpy).toHaveBeenCalledWith("mouseleave", expect.any(Function));

      // Verify cancelAnimationFrame was called to avoid leaking pending frame
      expect(global.cancelAnimationFrame).toHaveBeenCalled();
      expect(rafCallbacks.size).toBe(0);
    });

    it("handles dynamic prop change (trail 2 -> ambient true) by cleaning up listeners and canceling RAF", () => {
      const removeWindowSpy = vi.spyOn(window, "removeEventListener");

      const { rerender } = render(
        <Bubble trail={2} ambient={false}>
          <div>Child</div>
        </Bubble>
      );

      fireEvent.mouseMove(window, { clientX: 50, clientY: 50 });
      expect(rafCallbacks.size).toBe(1);

      // Rerender with ambient=true
      rerender(
        <Bubble trail={2} ambient={true}>
          <div>Child</div>
        </Bubble>
      );

      // Previous effect cleanup must run
      expect(removeWindowSpy).toHaveBeenCalledWith("mousemove", expect.any(Function));
      expect(global.cancelAnimationFrame).toHaveBeenCalled();
      expect(rafCallbacks.size).toBe(0);
    });
  });
});
