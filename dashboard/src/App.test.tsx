/**
 * @vitest-environment jsdom
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import App from "./App";
import * as useSSEHook from "./hooks/useSSE";

vi.mock("./hooks/useSSE", () => ({
  useSSE: vi.fn(),
}));

describe("App", () => {
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
});
