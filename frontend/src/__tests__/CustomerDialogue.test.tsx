import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import App from '../App';
import * as dialogueApi from '../api/customerDialogueApi';
import type { CallSessionResponse } from '../api/customerDialogueApi';

function makeCallSession(overrides: Partial<CallSessionResponse> = {}): CallSessionResponse {
  return {
    id: 'call-uuid-1',
    transaction_id: 'tx-uuid-1',
    conversation_id: 'conv-uuid-1',
    channel: 'VOICE_SIMULATED',
    status: 'RINGING',
    direction: 'OUTBOUND_SIMULATED',
    attempt_number: 1,
    customer_phone_masked: '+91 ••••• ••104',
    coercion_analysis_id: null,
    started_at: '2026-10-18T10:00:00Z',
    connected_at: null,
    ended_at: null,
    duration_seconds: null,
    failure_reason: null,
    turns: [
      {
        turn_index: 0,
        role: 'assistant',
        content: 'Hello, this is Aster Bank fraud prevention. Can you confirm the purpose of this ₹2,50,000 transfer?',
        evidence_references: ['amount', 'recipient_name'],
        risk_sentiment: 'neutral',
        confidence_score: 0.95,
        internal_observations: ['High-value payment to new recipient flagged for verification'],
        uncertainty_notes: [],
        suggested_action: 'INQUIRE_PURPOSE',
        is_terminal_turn: false,
        coercion_cues: [],
        created_at: '2026-10-18T10:00:00Z',
      },
    ],
    created_at: '2026-10-18T10:00:00Z',
    updated_at: '2026-10-18T10:00:00Z',
    ...overrides,
  };
}

describe('Dynamic Gemini-Powered Customer Dialogue (Option A)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.clearAllMocks();
  });

  describe('customerDialogueApi bindings', () => {
    it('initiateCallSessionApi sends POST request with correct payload', async () => {
      const mockSession = makeCallSession();
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => mockSession,
      });

      const res = await dialogueApi.initiateCallSessionApi('tx-uuid-1', {
        channel: 'VOICE_SIMULATED',
        idempotency_key: 'call-key-1',
      });

      expect(res.id).toBe('call-uuid-1');
      expect(res.status).toBe('RINGING');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/transactions/tx-uuid-1/calls'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ channel: 'VOICE_SIMULATED', idempotency_key: 'call-key-1' }),
        })
      );
    });

    it('connectCallSessionApi sends POST request to connect endpoint', async () => {
      const mockSession = makeCallSession({ status: 'CONNECTED', connected_at: '2026-10-18T10:00:05Z' });
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockSession,
      });

      const res = await dialogueApi.connectCallSessionApi('call-uuid-1');

      expect(res.status).toBe('CONNECTED');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/calls/call-uuid-1/connect'),
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('submitDialogueTurnApi sends customer message and source to turns endpoint', async () => {
      const mockSession = makeCallSession({
        status: 'CONNECTED',
        turns: [
          {
            turn_index: 0,
            role: 'assistant',
            content: 'Can you confirm the purpose of this transfer?',
            evidence_references: [],
            internal_observations: [],
            uncertainty_notes: [],
            suggested_action: 'INQUIRE_PURPOSE',
            is_terminal_turn: false,
            coercion_cues: [],
          },
          {
            turn_index: 1,
            role: 'customer',
            content: 'I was instructed by police officer Sharma to send this bond.',
            evidence_references: ['coercion_cues'],
            internal_observations: ['Law enforcement impersonation cues detected'],
            uncertainty_notes: [],
            suggested_action: 'INQUIRE_COERCION',
            is_terminal_turn: false,
            coercion_cues: ['authority_impersonation', 'arrest_threat'],
          },
          {
            turn_index: 2,
            role: 'assistant',
            content: 'Did this official ask you to stay on the phone and keep this transfer secret?',
            evidence_references: ['coercion_cues'],
            internal_observations: ['Probing secrecy and active call pressure'],
            uncertainty_notes: [],
            suggested_action: 'INQUIRE_SECRECY',
            is_terminal_turn: false,
            coercion_cues: ['secrecy_demand'],
          },
        ],
      });

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockSession,
      });

      const res = await dialogueApi.submitDialogueTurnApi('call-uuid-1', {
        customer_message: 'I was instructed by police officer Sharma to send this bond.',
        source: 'speech',
      });

      expect(res.turns.length).toBe(3);
      expect(res.turns[2].content).toContain('Did this official ask you');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/calls/call-uuid-1/turns'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            customer_message: 'I was instructed by police officer Sharma to send this bond.',
            source: 'speech',
          }),
        })
      );
    });

    it('completeCallSessionApi and declineCallSessionApi post to respective lifecycle endpoints', async () => {
      const completedSession = makeCallSession({ status: 'COMPLETED' });
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => completedSession,
      });

      const resComp = await dialogueApi.completeCallSessionApi('call-uuid-1');
      expect(resComp.status).toBe('COMPLETED');

      const declinedSession = makeCallSession({ status: 'DECLINED', failure_reason: 'User refused call' });
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => declinedSession,
      });

      const resDec = await dialogueApi.declineCallSessionApi('call-uuid-1', { reason: 'User refused call' });
      expect(resDec.status).toBe('DECLINED');
    });
  });

  describe('UI integration in CustomerPhone simulator', () => {
    it('initiates call session when payment is submitted, displays dynamic question, and handles chat turn', async () => {
      const mockCallSession = makeCallSession({
        turns: [
          {
            turn_index: 0,
            role: 'assistant',
            content: 'Aster Bank Security: What is the specific purpose of this transfer?',
            evidence_references: [],
            internal_observations: [],
            uncertainty_notes: [],
            suggested_action: 'INQUIRE_PURPOSE',
            is_terminal_turn: false,
            coercion_cues: [],
          },
        ],
      });

      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/api/v1/health')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ status: 'ready', database: 'connected' }),
          });
        }
        if (url.includes('/api/v1/transactions') && !url.includes('/calls')) {
          return Promise.resolve({
            ok: true,
            status: 201,
            json: async () => ({ id: 'tx-uuid-101' }),
          });
        }
        if (url.includes('/calls') && !url.includes('/turns') && !url.includes('/connect')) {
          return Promise.resolve({
            ok: true,
            status: 201,
            json: async () => mockCallSession,
          });
        }
        if (url.includes('/connect')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ ...mockCallSession, status: 'CONNECTED' }),
          });
        }
        if (url.includes('/turns')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({
              ...mockCallSession,
              status: 'CONNECTED',
              turns: [
                ...mockCallSession.turns,
                {
                  turn_index: 1,
                  role: 'customer',
                  content: 'Paying rent',
                  evidence_references: [],
                  internal_observations: [],
                  uncertainty_notes: [],
                  suggested_action: 'INQUIRE_CONFIRMATION',
                  is_terminal_turn: false,
                  coercion_cues: [],
                },
                {
                  turn_index: 2,
                  role: 'assistant',
                  content: 'Thank you. Did anyone advise you to keep this transaction confidential?',
                  evidence_references: [],
                  internal_observations: [],
                  uncertainty_notes: [],
                  suggested_action: 'INQUIRE_SECRECY',
                  is_terminal_turn: false,
                  coercion_cues: [],
                },
              ],
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({}),
        });
      });

      render(<App />);

      // Submit payment
      const sendButton = screen.getByTestId('phone-send-money');
      fireEvent.click(sendButton);

      // Verify ringing screen appears
      await waitFor(() => {
        expect(screen.getByTestId('incoming-call-screen')).toBeInTheDocument();
      });

      // Answer in chat
      const chatButton = screen.getByTestId('button-answer-in-chat');
      fireEvent.click(chatButton);

      // Verify connected in chat stage
      await waitFor(() => {
        expect(screen.getByTestId('phone-stage-chat')).toBeInTheDocument();
        expect(screen.getByTestId('phone-answer-input')).toBeInTheDocument();
      });

      // Insert example demo response
      const demoBtn = screen.getByTestId('button-demo-response');
      fireEvent.click(demoBtn);

      // Submit answer
      const submitBtn = screen.getByTestId('button-submit-answer');
      fireEvent.click(submitBtn);

      // Processing state should activate
      await waitFor(() => {
        expect(screen.getByTestId('phone-processing')).toBeInTheDocument();
      });
    });

    it('sends an idempotent client_turn_id when submitting a dialogue turn', async () => {
      const mockCallSession = makeCallSession({
        turns: [
          {
            turn_index: 0,
            role: 'assistant',
            content: 'Aster Bank Security: What is the specific purpose of this transfer?',
            evidence_references: [],
            internal_observations: [],
            uncertainty_notes: [],
            suggested_action: 'INQUIRE_PURPOSE',
            is_terminal_turn: false,
            coercion_cues: [],
          },
        ],
      });

      const fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/api/v1/health')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({ status: 'ready', database: 'connected' }) });
        }
        if (url.includes('/api/v1/transactions') && !url.includes('/calls')) {
          return Promise.resolve({ ok: true, status: 201, json: async () => ({ id: 'tx-uuid-202' }) });
        }
        if (url.includes('/calls') && !url.includes('/turns') && !url.includes('/connect')) {
          return Promise.resolve({ ok: true, status: 201, json: async () => mockCallSession });
        }
        if (url.includes('/connect')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({ ...mockCallSession, status: 'CONNECTED' }) });
        }
        if (url.includes('/turns')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ ...mockCallSession, status: 'CONNECTED' }),
          });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      });
      globalThis.fetch = fetchMock;

      render(<App />);

      fireEvent.click(screen.getByTestId('phone-send-money'));
      await waitFor(() => expect(screen.getByTestId('incoming-call-screen')).toBeInTheDocument());
      fireEvent.click(screen.getByTestId('button-answer-in-chat'));
      await waitFor(() => expect(screen.getByTestId('phone-answer-input')).toBeInTheDocument());
      fireEvent.click(screen.getByTestId('button-demo-response'));
      fireEvent.click(screen.getByTestId('button-submit-answer'));

      await waitFor(() => {
        const turnCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes('/turns'));
        expect(turnCalls.length).toBeGreaterThanOrEqual(1);
        const body = JSON.parse((turnCalls[0][1] as RequestInit).body as string);
        expect(typeof body.client_turn_id).toBe('string');
        expect(body.client_turn_id.length).toBeGreaterThan(0);
      });
    });

    it('handles call decline correctly', async () => {
      globalThis.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/api/v1/health')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ status: 'ready', database: 'connected' }),
          });
        }
        if (url.includes('/calls')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => makeCallSession(),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ id: 'tx-123' }),
        });
      });

      render(<App />);

      const sendButton = screen.getByTestId('phone-send-money');
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(screen.getByTestId('incoming-call-screen')).toBeInTheDocument();
      });

      const declineButton = screen.getByTestId('button-decline-call');
      fireEvent.click(declineButton);

      await waitFor(() => {
        expect(screen.getByTestId('phone-stage-incomplete')).toBeInTheDocument();
      });
    });
  });
});
