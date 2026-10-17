import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { HealthStatus } from "../components/HealthStatus";

describe("HealthStatus Component", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders loading state initially", () => {
    // Hang fetch promise to observe loading state
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

    render(<HealthStatus />);
    expect(screen.getByTestId("status-loading")).toBeInTheDocument();
    expect(screen.getByText(/Connecting to Backend.../i)).toBeInTheDocument();
  });

  it("displays connected state when backend responds with ready status", async () => {
    const mockSuccessResponse = {
      status: "ready",
      database: "connected",
      timestamp: "2026-10-17T12:00:00Z",
      environment: "test",
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSuccessResponse,
    });

    render(<HealthStatus />);

    await waitFor(() => {
      expect(screen.getByTestId("status-connected")).toBeInTheDocument();
    });

    expect(screen.getByText(/Connected & Ready/i)).toBeInTheDocument();
    expect(screen.getByTestId("db-status")).toHaveTextContent("connected");
    expect(screen.getByTestId("env-status")).toHaveTextContent("test");
  });

  it("displays error state when backend is unreachable or returns failure", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Network connection refused"));

    render(<HealthStatus />);

    await waitFor(() => {
      expect(screen.getByTestId("status-error")).toBeInTheDocument();
    });

    expect(screen.getByText(/Disconnected: Network connection refused/i)).toBeInTheDocument();
    expect(screen.getByTestId("db-status")).toHaveTextContent("Unavailable");
  });
});
