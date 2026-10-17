import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { InvestigationReviewPanel } from "../components/InvestigationReviewPanel";
import * as investigationApi from "../api/investigationApi";
import type {
  InvestigationResponse,
  InvestigationListResponse,
} from "../api/investigationApi";

function makeInvestigation(
  overrides: Partial<InvestigationResponse> = {}
): InvestigationResponse {
  return {
    id: "inv-1",
    transaction_id: "tx-1",
    assessment_id: "assess-1",
    summary: "Authority impersonation with coercion indicators.",
    overall_risk_sentiment: "COERCED",
    confidence: "HIGH",
    confidence_score: 0.94,
    findings: [
      {
        id: "FINDING-COERCION",
        category: "AUTHORITY_COERCION",
        explanation: "Caller impersonated law enforcement and demanded transfer.",
        severity: "CRITICAL",
        supporting_evidence_references: ["stmt_1", "telephony:screen_sharing_active"],
        source_provenance: "customer_statement",
      },
      {
        id: "FINDING-LEDGER",
        category: "LEGITIMATE_CONTEXT",
        explanation: "Historical ledger shows no prior relationship.",
        severity: "LOW",
        supporting_evidence_references: ["historical_ledger"],
        source_provenance: "historical_ledger",
      },
    ],
    contradictory_or_mitigating_evidence: ["Customer has a long tenure account."],
    missing_information: ["No independent confirmation of caller identity."],
    unresolved_questions: ["Was the customer instructed to stay on an active call?"],
    suggested_next_steps: ["Initiate simulated voice duress intervention."],
    model_metadata: {
      provider: "mock_gemini",
      model_id: "gemini-2.5-flash-mock",
      latency_ms: 42,
      correlation_id: "corr-1",
    },
    created_at: "2026-10-17T12:00:00Z",
    ...overrides,
  };
}

function listOf(items: InvestigationResponse[]): InvestigationListResponse {
  return { transaction_id: "tx-1", total_entries: items.length, items };
}

const baseProps = {
  transactionId: "tx-1",
  transactionReference: "AEG-REF-001",
  transactionStatus: "Awaiting verification",
  riskScore: 100,
  riskLevel: "CRITICAL",
};

describe("InvestigationReviewPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the overview with existing risk and investigation data", async () => {
    vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi").mockResolvedValue(
      listOf([makeInvestigation()])
    );
    render(<InvestigationReviewPanel {...baseProps} />);

    await waitFor(() =>
      expect(screen.getByTestId("review-overview")).toBeInTheDocument()
    );
    const overview = screen.getByTestId("review-overview");
    expect(within(overview).getByText("AEG-REF-001")).toBeInTheDocument();
    expect(within(overview).getByText("Awaiting verification")).toBeInTheDocument();
    expect(within(overview).getByText("CRITICAL (100/100)")).toBeInTheDocument();
    expect(within(overview).getByText("COERCED")).toBeInTheDocument();
    expect(within(overview).getByText("HIGH (94%)")).toBeInTheDocument();
    expect(
      within(overview).getByText(/mock_gemini · gemini-2.5-flash-mock/)
    ).toBeInTheDocument();
    // Must not describe the score as a calibrated probability.
    expect(
      screen.getByText(/a calibrated statistical fraud\s*probability/i)
    ).toBeInTheDocument();
  });

  it("renders findings sorted by severity with explanation and provenance", async () => {
    vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi").mockResolvedValue(
      listOf([makeInvestigation()])
    );
    render(<InvestigationReviewPanel {...baseProps} />);

    await waitFor(() => expect(screen.getByTestId("review-findings")).toBeInTheDocument());
    expect(screen.getByText("AUTHORITY_COERCION")).toBeInTheDocument();
    expect(
      screen.getByText(/Caller impersonated law enforcement/)
    ).toBeInTheDocument();
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    // Overall confidence is shown in the overview.
    expect(screen.getByText("HIGH (94%)")).toBeInTheDocument();

    // CRITICAL finding appears before the LOW finding in the DOM.
    const findings = screen.getByTestId("review-findings");
    const html = findings.innerHTML;
    expect(html.indexOf("AUTHORITY_COERCION")).toBeLessThan(html.indexOf("LEGITIMATE_CONTEXT"));
  });

  it("classifies provenance so unverified claims are not shown as verified", async () => {
    vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi").mockResolvedValue(
      listOf([makeInvestigation()])
    );
    render(<InvestigationReviewPanel {...baseProps} />);

    await waitFor(() => expect(screen.getByTestId("review-findings")).toBeInTheDocument());
    // Customer-statement finding is labeled unverified, NOT "independently verified".
    const coercion = screen.getByTestId("finding-provenance-FINDING-COERCION");
    expect(coercion).toHaveTextContent(/customer-reported \/ unverified/i);
    expect(coercion).not.toHaveTextContent(/independently verified/i);
    // Ledger-sourced finding is labeled independently verified.
    expect(screen.getByTestId("finding-provenance-FINDING-LEDGER")).toHaveTextContent(
      /independently verified/i
    );
  });

  it("builds an evidence index resolving references to the findings that cite them", async () => {
    vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi").mockResolvedValue(
      listOf([makeInvestigation()])
    );
    render(<InvestigationReviewPanel {...baseProps} />);

    await waitFor(() => expect(screen.getByTestId("review-evidence")).toBeInTheDocument());
    expect(screen.getByTestId("evidence-item-stmt_1")).toBeInTheDocument();
    expect(
      screen.getByTestId("evidence-item-telephony:screen_sharing_active")
    ).toBeInTheDocument();
    expect(screen.getByTestId("evidence-item-historical_ledger")).toBeInTheDocument();
    // Evidence content is explicitly flagged as not retained (no fabrication).
    expect(
      screen.getAllByText(/Source content is not retained/i).length
    ).toBeGreaterThan(0);
  });

  it("keeps uncertainty and missing information visible in their own sections", async () => {
    vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi").mockResolvedValue(
      listOf([makeInvestigation()])
    );
    render(<InvestigationReviewPanel {...baseProps} />);

    await waitFor(() => expect(screen.getByTestId("review-uncertainty")).toBeInTheDocument());
    expect(
      within(screen.getByTestId("review-missing-information")).getByText(
        /No independent confirmation of caller identity/
      )
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("review-unresolved-questions")).getByText(
        /stay on an active call/
      )
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("review-contradictory-evidence")).getByText(
        /long tenure account/
      )
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("review-next-steps")).getByText(
        /simulated voice duress intervention/
      )
    ).toBeInTheDocument();
  });

  it("renders a clear empty state when there is no investigation", async () => {
    vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi").mockResolvedValue(
      listOf([])
    );
    render(<InvestigationReviewPanel {...baseProps} />);
    await waitFor(() =>
      expect(screen.getByTestId("review-empty-state")).toBeInTheDocument()
    );
    expect(screen.getByText(/No AI investigation recorded/i)).toBeInTheDocument();
  });

  it("treats a 404 (unknown transaction) as an empty state, not an error", async () => {
    vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi").mockRejectedValue(
      new Error("Failed to fetch investigations for transaction tx-1 (404): not found")
    );
    render(<InvestigationReviewPanel {...baseProps} />);
    await waitFor(() =>
      expect(screen.getByTestId("review-empty-state")).toBeInTheDocument()
    );
    expect(screen.queryByTestId("review-error-alert")).not.toBeInTheDocument();
  });

  it("does not crash on partial/missing optional fields", async () => {
    vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi").mockResolvedValue(
      listOf([
        makeInvestigation({
          summary: "",
          findings: [],
          missing_information: [],
          unresolved_questions: [],
          contradictory_or_mitigating_evidence: [],
          suggested_next_steps: [],
        }),
      ])
    );
    render(
      <InvestigationReviewPanel
        transactionId="tx-1"
        transactionReference="AEG-REF-002"
        transactionStatus="Awaiting verification"
        riskScore={null}
        riskLevel={null}
      />
    );
    await waitFor(() => expect(screen.getByTestId("review-content")).toBeInTheDocument());
    // Risk not available is shown rather than a fabricated score.
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText(/recorded no discrete findings/i)).toBeInTheDocument();
  });

  it("renders the error state on a non-404 API failure", async () => {
    vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi").mockRejectedValue(
      new Error("Failed to fetch investigations for transaction tx-1 (500): server error")
    );
    render(<InvestigationReviewPanel {...baseProps} />);
    await waitFor(() =>
      expect(screen.getByTestId("review-error-alert")).toBeInTheDocument()
    );
  });

  it("uses the authenticated investigation API client and refreshes on demand", async () => {
    const spy = vi
      .spyOn(investigationApi, "fetchInvestigationsForTransactionApi")
      .mockResolvedValue(listOf([makeInvestigation()]));
    render(<InvestigationReviewPanel {...baseProps} />);
    await waitFor(() => expect(screen.getByTestId("review-content")).toBeInTheDocument());
    expect(spy).toHaveBeenCalledWith("tx-1");
    expect(spy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("button-refresh-investigation"));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
  });

  it("does not issue duplicate fetches from rapid repeated refresh clicks", async () => {
    let resolveSecond: (v: InvestigationListResponse) => void = () => {};
    const spy = vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi");
    // First (mount) resolves immediately; the refresh call stays pending.
    spy.mockResolvedValueOnce(listOf([makeInvestigation()]));
    spy.mockImplementationOnce(
      () =>
        new Promise<InvestigationListResponse>((res) => {
          resolveSecond = res;
        })
    );

    render(<InvestigationReviewPanel {...baseProps} />);
    await waitFor(() => expect(screen.getByTestId("review-content")).toBeInTheDocument());
    expect(spy).toHaveBeenCalledTimes(1);

    const btn = screen.getByTestId("button-refresh-investigation");
    fireEvent.click(btn); // starts the pending (2nd) fetch
    fireEvent.click(btn); // blocked: button disabled + in-flight guard
    fireEvent.click(btn);
    // Only one additional in-flight request was issued.
    expect(spy).toHaveBeenCalledTimes(2);

    resolveSecond(listOf([makeInvestigation()]));
    await waitFor(() => expect(screen.getByTestId("review-content")).toBeInTheDocument());
  });

  it("refreshes findings after further investigation", async () => {
    const spy = vi.spyOn(investigationApi, "fetchInvestigationsForTransactionApi");
    spy.mockResolvedValueOnce(listOf([makeInvestigation()]));
    spy.mockResolvedValueOnce(
      listOf([
        makeInvestigation({
          id: "inv-2",
          findings: [
            {
              id: "FINDING-NEW",
              category: "MULE_VELOCITY",
              explanation: "Beneficiary matches consortium mule registry.",
              severity: "CRITICAL",
              supporting_evidence_references: ["consortium_registry"],
              source_provenance: "consortium_registry",
            },
          ],
        }),
      ])
    );

    render(<InvestigationReviewPanel {...baseProps} />);
    await waitFor(() => expect(screen.getByText("AUTHORITY_COERCION")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("button-refresh-investigation"));
    await waitFor(() => expect(screen.getByText("MULE_VELOCITY")).toBeInTheDocument());
    expect(screen.queryByText("AUTHORITY_COERCION")).not.toBeInTheDocument();
  });
});
