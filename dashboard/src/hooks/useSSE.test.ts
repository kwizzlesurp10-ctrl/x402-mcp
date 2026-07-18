/**
 * @vitest-environment jsdom
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backoffMs } from "./sseReconnect";
import { useSSE } from "./useSSE";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }
}

describe("useSSE", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reconnects after onerror and returns live on second onopen", () => {
    const onEvent = vi.fn();
    const { result } = renderHook(() => useSSE(true, onEvent));

    expect(MockEventSource.instances).toHaveLength(1);
    const first = MockEventSource.instances[0];

    act(() => {
      first.onerror?.();
    });
    expect(result.current.status).toBe("polling");
    expect(first.closed).toBe(true);

    act(() => {
      vi.advanceTimersByTime(backoffMs(0));
    });

    expect(MockEventSource.instances).toHaveLength(2);
    act(() => {
      MockEventSource.instances[1].onopen?.();
    });
    expect(result.current.status).toBe("live");
  });

  it("sets live on heartbeat without emitting tool events", () => {
    const onEvent = vi.fn();
    const { result } = renderHook(() => useSSE(true, onEvent));

    const es = MockEventSource.instances[0];
    act(() => {
      es.onmessage?.({
        data: JSON.stringify({ type: "heartbeat", ts: "2026-07-10T00:00:00Z" }),
      } as MessageEvent);
    });

    expect(onEvent).not.toHaveBeenCalled();
    expect(result.current.status).toBe("live");
  });
});