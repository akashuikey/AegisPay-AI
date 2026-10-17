import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { InvestigationConversationPanel } from "../components/InvestigationConversationPanel";
import * as investigationApi from "../api/investigationApi";

describe("InvestigationConversationPanel", () => {
  const mockTransactionId = "tx-conv-test-123";
  const mockRecipient = "Cyber Police Verification Escrow";
  const mockAmount = 250000;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state and allows starting a conversation when no conversation exists", async () => {
    vi.spyOn(investigationApi, "getCurrentConversationForTransactionApi").mockResolvedValue(null);
    const startSpy = vi.spyOn(investigationApi, "startInvestigationConversationApi").mockResolvedValue({
      id: "conv-1",
      transaction_id: mockTransactionId,
      status: "ACTIVE",
      turn_count: 1,
      version: 1,
      turns: [
        {
          id: "turn-1",
          conversation_id: "conv-1",
          turn_index: 0,
          role: "operator",
          content: "Customer claims call is from police.",
          evidence_provenance: "customer_statement",
          evidence_references: [],
          findings: [],
          risk_sentiment: null,
          confidence: null,
          confidence_score: null,
          missing_information: [],
          follow_up_questions: [],
          model_metadata: { provider: "mock" },
          created_at: "2026-10-17T12:00:00Z",
        },
      ],
      created_at: "2026-10-17T12:00:00Z",
      updated_at: "2026-10-17T12:00:00Z",
    });

    render(
      <InvestigationConversationPanel
        transactionId={mockTransactionId}
        transactionRecipient={mockRecipient}
        transactionAmount={mockAmount}
      />
    );

    // Initial loading indicator then empty state
    await waitFor(() => {
      expect(screen.getByText(/No Active Investigation Conversation/i)).toBeInTheDocument();
    });

    expect(screen.getByTestId("button-start-conversation")).toBeInTheDocument();

    // Type input and click start
    const input = screen.getByTestId("input-initial-conversation");
    fireEvent.change(input, { target: { value: "Customer claims call is from police." } });

    fireEvent.click(screen.getByTestId("button-start-conversation"));

    await waitFor(() => {
      expect(startSpy).toHaveBeenCalledWith(mockTransactionId, {
        initial_message: "Customer claims call is from police.",
        evidence_provenance: "customer_statement",
      });
    });

    // Check updated conversation rendered
    await waitFor(() => {
      expect(screen.getByText(/Customer claims call is from police\./i)).toBeInTheDocument();
    });
  });

  it("renders active conversation with AI findings, risk sentiment, and follow-up inquiry chips", async () => {
    vi.spyOn(investigationApi, "getCurrentConversationForTransactionApi").mockResolvedValue({
      id: "conv-2",
      transaction_id: mockTransactionId,
      status: "ACTIVE",
      turn_count: 2,
      version: 2,
      turns: [
        {
          id: "turn-1",
          conversation_id: "conv-2",
          turn_index: 0,
          role: "operator",
          content: "The customer is on an active call and crying.",
          evidence_provenance: "device_telephony",
          evidence_references: [],
          findings: [],
          risk_sentiment: null,
          confidence: null,
          confidence_score: null,
          missing_information: [],
          follow_up_questions: [],
          model_metadata: { provider: "vertex_ai" },
          created_at: "2026-10-17T12:00:00Z",
        },
        {
          id: "turn-2",
          conversation_id: "conv-2",
          turn_index: 1,
          role: "assistant",
          content: "Analysis of the call context indicates severe distress and coercion tactics.",
          evidence_provenance: "ai_assistant",
          risk_sentiment: "COERCED",
          confidence: "HIGH",
          confidence_score: 0.95,
          evidence_references: ["customer is on an active call and crying"],
          findings: [
            {
              id: "f-1",
              category: "AUTHORITY_COERCION",
              explanation: "Customer appears under duress while speaking to caller.",
              severity: "CRITICAL",
              supporting_evidence_references: ["customer is on an active call and crying"],
              source_provenance: "customer_statement",
            },
          ],
          missing_information: ["Caller phone number and true organization"],
          follow_up_questions: [
            "Did the caller state the customer's funds would be seized?",
          ],
          model_metadata: { provider: "vertex_ai" },
          created_at: "2026-10-17T12:01:00Z",
        },
      ],
      created_at: "2026-10-17T12:00:00Z",
      updated_at: "2026-10-17T12:01:00Z",
    });

    render(
      <InvestigationConversationPanel
        transactionId={mockTransactionId}
        transactionRecipient={mockRecipient}
        transactionAmount={mockAmount}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("investigation-conversation-panel")).toBeInTheDocument();
    });

    // Check badges and header
    expect(screen.getByText(/AI Forensic Investigation Dialogue/i)).toBeInTheDocument();
    expect(screen.getByText(/Turns: 2\/20/i)).toBeInTheDocument();
    expect(screen.getByText(/Vertex AI/i)).toBeInTheDocument();
    expect(screen.getByText(/Risk Sentiment: COERCED/i)).toBeInTheDocument();

    // Check operator turn content
    expect(screen.getByText(/The customer is on an active call and crying\./i)).toBeInTheDocument();

    // Check assistant turn content
    expect(screen.getByText(/Analysis of the call context indicates severe distress/i)).toBeInTheDocument();

    // Check findings
    expect(screen.getByText(/AUTHORITY_COERCION/i)).toBeInTheDocument();
    expect(screen.getByText(/Customer appears under duress while speaking to caller\./i)).toBeInTheDocument();

    // Check follow-up inquiry chips
    const chip = screen.getByTestId("chip-follow-up-0");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveTextContent(/Did the caller state the customer's funds would be seized\?/i);

    // Clicking the inquiry chip should populate the turn message textarea with answer prompt
    fireEvent.click(chip);
    const textarea = screen.getByTestId("input-conversation-turn") as HTMLTextAreaElement;
    expect(textarea.value).toBe('Customer answer to "Did the caller state the customer\'s funds would be seized?": ');
  });

  it("submits a new turn when sending a message", async () => {
    vi.spyOn(investigationApi, "getCurrentConversationForTransactionApi").mockResolvedValue({
      id: "conv-3",
      transaction_id: mockTransactionId,
      status: "ACTIVE",
      turn_count: 1,
      version: 1,
      turns: [
        {
          id: "turn-1",
          conversation_id: "conv-3",
          turn_index: 0,
          role: "operator",
          content: "Initial statement",
          evidence_provenance: "customer_statement",
          evidence_references: [],
          findings: [],
          risk_sentiment: null,
          confidence: null,
          confidence_score: null,
          missing_information: [],
          follow_up_questions: [],
          model_metadata: { provider: "mock" },
          created_at: "2026-10-17T12:00:00Z",
        },
      ],
      created_at: "2026-10-17T12:00:00Z",
      updated_at: "2026-10-17T12:00:00Z",
    });

    const submitSpy = vi.spyOn(investigationApi, "submitConversationTurnApi").mockResolvedValue({
      id: "conv-3",
      transaction_id: mockTransactionId,
      status: "ACTIVE",
      turn_count: 3,
      version: 3,
      turns: [
        {
          id: "turn-1",
          conversation_id: "conv-3",
          turn_index: 0,
          role: "operator",
          content: "Initial statement",
          evidence_provenance: "customer_statement",
          evidence_references: [],
          findings: [],
          risk_sentiment: null,
          confidence: null,
          confidence_score: null,
          missing_information: [],
          follow_up_questions: [],
          model_metadata: { provider: "mock" },
          created_at: "2026-10-17T12:00:00Z",
        },
        {
          id: "turn-2",
          conversation_id: "conv-3",
          turn_index: 1,
          role: "operator",
          content: "Caller told customer funds are seized",
          evidence_provenance: "customer_statement",
          evidence_references: [],
          findings: [],
          risk_sentiment: null,
          confidence: null,
          confidence_score: null,
          missing_information: [],
          follow_up_questions: [],
          model_metadata: { provider: "mock" },
          created_at: "2026-10-17T12:02:00Z",
        },
        {
          id: "turn-3",
          conversation_id: "conv-3",
          turn_index: 2,
          role: "assistant",
          content: "Seizure threat confirms digital arrest playbook.",
          evidence_provenance: "ai_assistant",
          risk_sentiment: "MALICIOUS",
          confidence: "HIGH",
          confidence_score: 0.98,
          evidence_references: ["funds are seized"],
          findings: [
            {
              id: "f-3",
              category: "AUTHORITY_COERCION",
              explanation: "Law enforcement impersonation threat.",
              severity: "CRITICAL",
              supporting_evidence_references: ["funds are seized"],
              source_provenance: "customer_statement",
            },
          ],
          missing_information: [],
          follow_up_questions: [],
          model_metadata: { provider: "mock" },
          created_at: "2026-10-17T12:02:05Z",
        },
      ],
      created_at: "2026-10-17T12:00:00Z",
      updated_at: "2026-10-17T12:02:05Z",
    });

    render(
      <InvestigationConversationPanel
        transactionId={mockTransactionId}
        transactionRecipient={mockRecipient}
        transactionAmount={mockAmount}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Initial statement/i)).toBeInTheDocument();
    });

    const textarea = screen.getByTestId("input-conversation-turn");
    fireEvent.change(textarea, { target: { value: "Caller told customer funds are seized" } });

    const sendButton = screen.getByTestId("button-send-conversation-turn");
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(submitSpy).toHaveBeenCalledWith(
        "conv-3",
        expect.objectContaining({
          content: "Caller told customer funds are seized",
          evidence_provenance: "customer_statement",
        }),
        mockTransactionId
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/Seizure threat confirms digital arrest playbook\./i)).toBeInTheDocument();
    });
  });

  it("displays non-mutation advisory clearly in the panel footer", async () => {
    vi.spyOn(investigationApi, "getCurrentConversationForTransactionApi").mockResolvedValue({
      id: "conv-4",
      transaction_id: mockTransactionId,
      status: "ACTIVE",
      turn_count: 1,
      version: 1,
      turns: [
        {
          id: "turn-1",
          conversation_id: "conv-4",
          turn_index: 0,
          role: "operator",
          content: "Hello",
          evidence_provenance: "operator_note",
          evidence_references: [],
          findings: [],
          risk_sentiment: null,
          confidence: null,
          confidence_score: null,
          missing_information: [],
          follow_up_questions: [],
          model_metadata: { provider: "mock" },
          created_at: "2026-10-17T12:00:00Z",
        },
      ],
      created_at: "2026-10-17T12:00:00Z",
      updated_at: "2026-10-17T12:00:00Z",
    });

    render(
      <InvestigationConversationPanel
        transactionId={mockTransactionId}
        transactionRecipient={mockRecipient}
        transactionAmount={mockAmount}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Forensic Intelligence Only:/i)).toBeInTheDocument();
      expect(
        screen.getByText(/never mutates transaction workflow state/i)
      ).toBeInTheDocument();
    });
  });
});
