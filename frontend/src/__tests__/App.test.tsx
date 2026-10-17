import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
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

  it("renders the 6-metric summary cards and payment activity table with risk scores", () => {
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

    // Risk score column
    expect(screen.getByRole("columnheader", { name: /Risk score/i })).toBeInTheDocument();
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

  it("provides all 6 benchmark demo scenarios in presenter controls", () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    render(<App />);

    const select = screen.getByTestId("select-scenario") as HTMLSelectElement;
    expect(select).toBeInTheDocument();

    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).toContain("digital_arrest");
    expect(optionValues).toContain("investment_scam");
    expect(optionValues).toContain("fake_invoice");
    expect(optionValues).toContain("mule_network");
    expect(optionValues).toContain("legitimate_high_value");
    expect(optionValues).toContain("ambiguous_payment");
  });

  it("renders deterministic risk assessment tab and details in the transaction drawer", async () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    render(<App />);

    // Click on Leela Menon's row (which has a HIGH risk assessment from coercion/call)
    const row = screen.getByTestId("row-transaction-AST-240618-0824");
    fireEvent.click(row);

    // Verify transaction drawer is open
    expect(screen.getByTestId("transaction-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("drawer-risk-level")).toBeInTheDocument();

    // Switch to Risk assessment tab
    const riskTab = screen.getByTestId("drawer-tab-risk-assessment");
    fireEvent.click(riskTab);

    // Verify Risk section rendered
    expect(screen.getByTestId("drawer-risk-section")).toBeInTheDocument();
    expect(screen.getByTestId("drawer-risk-tier")).toHaveTextContent("HIGH");
    expect(screen.getByTestId("drawer-recommended-action")).toHaveTextContent("HOLD_FOR_INVESTIGATION");
    expect(screen.getByTestId("triggered-rules-list")).toBeInTheDocument();
    expect(screen.getByTestId("missing-evidence-list")).toBeInTheDocument();
  });
});
