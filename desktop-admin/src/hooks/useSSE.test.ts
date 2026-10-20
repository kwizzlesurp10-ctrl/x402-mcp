/**
 * @vitest-environment jsdom
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

  it("reconnects EventSource when apiBase changes", () => {
    const onEvent = vi.fn();
    const { rerender } = renderHook(
      ({ apiBase }) => useSSE(true, onEvent, apiBase),
      { initialProps: { apiBase: "http://127.0.0.1:8402" } },
    );

    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe("http://127.0.0.1:8402/events");
    expect(MockEventSource.instances[0].closed).toBe(false);

    rerender({ apiBase: "http://localhost:9000" });

    expect(MockEventSource.instances[0].closed).toBe(true);
    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1].url).toBe("http://localhost:9000/events");
  });

  it("closes the previous EventSource on unmount", () => {
    const onEvent = vi.fn();
    const { unmount } = renderHook(() => useSSE(true, onEvent, "/api"));

    const es = MockEventSource.instances[0];
    act(() => {
      unmount();
    });
    expect(es.closed).toBe(true);
  });
});
