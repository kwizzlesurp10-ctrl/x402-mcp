/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, it, expect, vi } from "vitest";
import App from "./App";
import * as useSSEHook from "./hooks/useSSE";

vi.mock("./hooks/useSSE", () => ({
  useSSE: vi.fn(),
}));

const memoryStore: Record<string, string> = {};
vi.stubGlobal("localStorage", {
  getItem: (key: string) => memoryStore[key] ?? null,
  setItem: (key: string, value: string) => {
    memoryStore[key] = value;
  },
  removeItem: (key: string) => {
    delete memoryStore[key];
  },
  clear: () => {
    for (const key of Object.keys(memoryStore)) delete memoryStore[key];
  },
  key: (index: number) => Object.keys(memoryStore)[index] ?? null,
  get length() {
    return Object.keys(memoryStore).length;
  },
});

describe("App", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders disconnected error panel when serverStatus is disconnected", () => {
    vi.mocked(useSSEHook.useSSE).mockReturnValue({
      status: "disconnected",
      reconnect: vi.fn(),
    });

    render(<App />);

    expect(screen.getByText("Disconnected")).toBeDefined();
    expect(screen.getByText(/Dashboard can't reach the server/i)).toBeDefined();
    expect(screen.getByText("Retry Connection")).toBeDefined();
  });

  it("does not render disconnected error panel when connected", () => {
    vi.mocked(useSSEHook.useSSE).mockReturnValue({
      status: "connected",
      reconnect: vi.fn(),
    });

    render(<App />);

    expect(screen.queryByText("Disconnected")).toBeNull();
  });

  it("does not costume the live dashboard as a Private Operator Terminal", () => {
    vi.mocked(useSSEHook.useSSE).mockReturnValue({
      status: "connected",
      reconnect: vi.fn(),
    });

    render(<App />);

    expect(screen.queryByText(/Private Operator Terminal/i)).toBeNull();
    expect(screen.queryByText(/Public Ecosystem Showcase/i)).toBeNull();
    expect(screen.getByLabelText("Demo")).toBeDefined();
  });
});
