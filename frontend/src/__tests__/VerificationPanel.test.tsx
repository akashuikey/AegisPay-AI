import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { VerificationPanel } from "../components/VerificationPanel";
import * as verificationApi from "../api/verificationApi";
import type {
  ChallengeResponse,
  SubmitVerificationResponse,
} from "../api/verificationApi";

function makeChallenge(overrides: Partial<ChallengeResponse> = {}): ChallengeResponse {
  return {
    challenge_id: "ch-1",
    transaction_id: "tx-1",
    status: "PENDING",
    attempt_count: 0,
    max_attempts: 5,
    attempts_remaining: 5,
    expires_at: "2026-10-18T12:05:00Z",
    customer_session_token: "cust.session.token",
    session_expires_in: 600,
    simulated: true,
    dev_otp: "123456",
    ...overrides,
  };
}

function makeSubmit(overrides: Partial<SubmitVerificationResponse> = {}): SubmitVerificationResponse {
  return {
    challenge_id: "ch-1",
    transaction_id: "tx-1",
    result: "SUCCEEDED",
    status: "CONSUMED",
    attempts_remaining: 5,
    transaction_state: "SETTLED_SIMULATED",
    decision: {
      id: "dec-1",
      transaction_id: "tx-1",
      transaction_state: "SETTLED_SIMULATED",
      policy_version: "p2a4.v1",
      action: "ALLOW",
      risk_score: 30,
      risk_level: "MEDIUM",
      requires_verification: false,
      provider_failed: false,
      investigation_performed: false,
      from_state: "DECISION_READY",
      to_state: "SETTLED_SIMULATED",
      workflow_status: "ALLOWED_SETTLED",
      reason_codes: ["VERIFICATION_SATISFIED"],
      triggered_rule_ids: [],
      investigation_finding_refs: [],
      supporting_evidence_refs: [],
      missing_information: [],
      explanation: "Verification satisfied; simulated settlement.",
      simulated: true,
      created_at: "2026-10-18T12:01:00Z",
    },
    simulated: true,
    ...overrides,
  };
}

describe("VerificationPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("creates a challenge and shows the simulated OTP clearly labeled", async () => {
    vi.spyOn(verificationApi, "createChallengeApi").mockResolvedValue(makeChallenge());
    render(<VerificationPanel transactionId="tx-1" />);
    fireEvent.click(screen.getByTestId("button-create-challenge"));

    await waitFor(() => expect(screen.getByTestId("verification-pending")).toBeInTheDocument());
    const otpBanner = screen.getByTestId("verification-dev-otp");
    expect(otpBanner).toHaveTextContent("123456");
    expect(otpBanner).toHaveTextContent(/simulated/i);
    expect(screen.getByText(/not a real bank authentication channel/i)).toBeInTheDocument();
  });

  it("submits the OTP and shows the resulting simulated decision", async () => {
    vi.spyOn(verificationApi, "createChallengeApi").mockResolvedValue(makeChallenge());
    const submitSpy = vi
      .spyOn(verificationApi, "submitVerificationApi")
      .mockResolvedValue(makeSubmit());
    render(<VerificationPanel transactionId="tx-1" />);
    fireEvent.click(screen.getByTestId("button-create-challenge"));
    await waitFor(() => expect(screen.getByTestId("input-otp")).toBeInTheDocument());

    fireEvent.change(screen.getByTestId("input-otp"), { target: { value: "123456" } });
    fireEvent.click(screen.getByTestId("button-submit-otp"));

    await waitFor(() => expect(screen.getByTestId("verification-resolved")).toBeInTheDocument());
    expect(screen.getByTestId("verification-decision-action")).toHaveTextContent("ALLOW");
    expect(submitSpy).toHaveBeenCalledWith("ch-1", "cust.session.token", "123456");
    // Simulated outcome is clearly labeled in the resolved section.
    const resolved = screen.getByTestId("verification-resolved");
    expect(resolved).toHaveTextContent(/simulated outcome/i);
    expect(resolved).toHaveTextContent(/not a real bank transfer/i);
  });

  it("shows a failed attempt and keeps the challenge pending with decremented attempts", async () => {
    vi.spyOn(verificationApi, "createChallengeApi").mockResolvedValue(makeChallenge());
    vi.spyOn(verificationApi, "submitVerificationApi").mockResolvedValue(
      makeSubmit({ result: "FAILED", status: "PENDING", attempts_remaining: 4, decision: null })
    );
    render(<VerificationPanel transactionId="tx-1" />);
    fireEvent.click(screen.getByTestId("button-create-challenge"));
    await waitFor(() => expect(screen.getByTestId("input-otp")).toBeInTheDocument());

    fireEvent.change(screen.getByTestId("input-otp"), { target: { value: "000000" } });
    fireEvent.click(screen.getByTestId("button-submit-otp"));

    await waitFor(() =>
      expect(screen.getByTestId("verification-failed-note")).toHaveTextContent(/4 attempt/i)
    );
    expect(screen.getByTestId("verification-attempts")).toHaveTextContent("4");
    expect(screen.queryByTestId("verification-resolved")).not.toBeInTheDocument();
  });

  it("surfaces an error when challenge creation is not applicable", async () => {
    vi.spyOn(verificationApi, "createChallengeApi").mockRejectedValue(
      new Error("Transaction does not currently require verification")
    );
    render(<VerificationPanel transactionId="tx-1" />);
    fireEvent.click(screen.getByTestId("button-create-challenge"));
    await waitFor(() => expect(screen.getByTestId("verification-error")).toBeInTheDocument());
    expect(screen.getByTestId("verification-error")).toHaveTextContent(/require verification/i);
  });

  it("only validates digits and requires a minimum length before submitting", async () => {
    vi.spyOn(verificationApi, "createChallengeApi").mockResolvedValue(makeChallenge());
    render(<VerificationPanel transactionId="tx-1" />);
    fireEvent.click(screen.getByTestId("button-create-challenge"));
    await waitFor(() => expect(screen.getByTestId("input-otp")).toBeInTheDocument());

    const input = screen.getByTestId("input-otp") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "12ab" } });
    expect(input.value).toBe("12"); // non-digits stripped
    expect(screen.getByTestId("button-submit-otp")).toBeDisabled();
  });
});
