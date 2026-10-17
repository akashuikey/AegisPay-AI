import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../App";

describe("AegisPay AI / Aster Bank Console & Phone Simulator", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("renders the Aster Bank operations console header and branding", () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    render(<App />);

    expect(screen.getAllByText(/Aster/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Operations workspace/i)).toBeInTheDocument();
    expect(screen.getByText(/DEMO \/ SIMULATED/i)).toBeInTheDocument();
  });

  it("renders the 6-metric summary cards and payment activity table", () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    render(<App />);

    expect(screen.getByText(/Live payment console/i)).toBeInTheDocument();
    expect(screen.getByText(/Payments today/i)).toBeInTheDocument();
    expect(screen.getByText(/Active verifications/i)).toBeInTheDocument();
    expect(screen.getByText(/Completed payments/i)).toBeInTheDocument();

    // Table rows
    expect(screen.getByText(/Meera Iyer/i)).toBeInTheDocument();
    expect(screen.getByText(/Kabir Shah/i)).toBeInTheDocument();
    expect(screen.getByText(/Sana Kapoor/i)).toBeInTheDocument();
  });

  it("renders the customer mobile phone simulator", () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    render(<App />);

    expect(screen.getByText(/CUSTOMER DEVICE · ANDROID PREVIEW/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Send money/i).length).toBeGreaterThan(0);
  });

  it("connects to backend health probe and displays live status badge", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        status: "ready",
        database: "connected",
        timestamp: "2026-10-17T12:00:00Z",
        environment: "development",
      }),
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("backend-health-badge")).toBeInTheDocument();
      expect(screen.getByText(/API Online/i)).toBeInTheDocument();
    });
  });
});

