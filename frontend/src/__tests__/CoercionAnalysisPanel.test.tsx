import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CoercionAnalysisPanel } from '../components/CoercionAnalysisPanel';
import * as coercionApi from '../api/coercionApi';

vi.mock('../api/coercionApi', () => ({
  getCoercionLifecycleApi: vi.fn(),
  analyzeCoercionApi: vi.fn(),
}));

const notStarted = {
  status: 'not_started' as const,
  detail: 'No coercion analysis has been performed for this transaction yet.',
  analysis: null,
};

describe('CoercionAnalysisPanel', () => {
  const transactionId = '00000000-0000-0000-0000-000000000001';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial state and fetches existing analysis (null)', async () => {
    vi.mocked(coercionApi.getCoercionLifecycleApi).mockResolvedValueOnce(notStarted);

    render(<CoercionAnalysisPanel transactionId={transactionId} />);

    expect(screen.getByTestId('coercion-analysis-panel')).toBeInTheDocument();
    expect(screen.getByText(/Voice Duress & Coercion Intelligence/i)).toBeInTheDocument();
    expect(screen.getByTestId('coercion-transcript-input')).toBeInTheDocument();
    expect(screen.getByTestId('coercion-analyze-button')).toBeDisabled();

    await waitFor(() => {
      expect(coercionApi.getCoercionLifecycleApi).toHaveBeenCalledWith(transactionId);
    });
  });

  it('renders existing coercion analysis with confirmed level, findings, and disclaimer', async () => {
    const mockAnalysis: coercionApi.CoercionAnalysisResponse = {
      id: 'analysis-123',
      transaction_id: transactionId,
      overall_coercion_level: 'CONFIRMED_COERCION',
      confidence: 'HIGH',
      confidence_score: 0.92,
      summary: 'Extreme authority pressure with digital arrest threat detected.',
      findings: [
        {
          id: 'COERCION-1',
          category: 'AUTHORITY_IMPERSONATION',
          severity: 'CRITICAL',
          is_explicit: true,
          explanation: 'Caller impersonates CBI headquarters officer.',
          supporting_excerpt: 'This is Inspector Sharma from Cyber Crime CBI Headquarters.',
          provenance: 'simulated_call_transcript',
        },
      ],
      voice_stress_signals: {
        detected: true,
        level: 'HIGH',
        acoustic_indicators: ['micro-tremors', 'frequency modulation'],
        speech_rate_wpm: 195,
        provenance: 'simulated_acoustic_telemetry',
        is_simulated: true,
        disclaimer:
          'Simulated acoustic indicator; voice stress is advisory only and not proof of deception or fraud.',
      },
      legitimate_explanations: [],
      uncertainty_notes: ['Background room reverberation noticed'],
      missing_information: [],
      model_metadata: {
        provider: 'mock',
        model_id: 'mock-gemini-pro',
        latency_ms: 120,
      },
      status: 'COMPLETED',
      transcript_snippet: 'This is Inspector Sharma...',
      created_at: '2026-10-18T00:00:00Z',
    };

    vi.mocked(coercionApi.getCoercionLifecycleApi).mockResolvedValueOnce({ status: 'completed', detail: '', analysis: mockAnalysis });

    render(<CoercionAnalysisPanel transactionId={transactionId} />);

    await waitFor(() => {
      expect(screen.getByTestId('coercion-result-card')).toBeInTheDocument();
    });

    expect(screen.getByTestId('coercion-level-badge')).toHaveTextContent('CONFIRMED_COERCION');
    expect(screen.getByText(/Extreme authority pressure/i)).toBeInTheDocument();
    expect(screen.getByTestId('voice-stress-card')).toBeInTheDocument();
    expect(screen.getByText(/STRESS: HIGH/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Simulated acoustic indicator; voice stress is advisory only/i)
    ).toBeInTheDocument();

    expect(screen.getByTestId('coercion-finding-COERCION-1')).toBeInTheDocument();
    expect(
      screen.getByText(/"This is Inspector Sharma from Cyber Crime CBI Headquarters."/i)
    ).toBeInTheDocument();
  });

  it('submits a transcript and updates analysis', async () => {
    vi.mocked(coercionApi.getCoercionLifecycleApi).mockResolvedValueOnce(notStarted);

    const newAnalysis: coercionApi.CoercionAnalysisResponse = {
      id: 'analysis-456',
      transaction_id: transactionId,
      overall_coercion_level: 'NONE',
      confidence: 'HIGH',
      confidence_score: 0.88,
      summary: 'Legitimate personal rent transfer confirmed by conversation dialogue.',
      findings: [],
      legitimate_explanations: ['Customer explicitly books an apartment with verified flat owner.'],
      uncertainty_notes: [],
      missing_information: [],
      model_metadata: {
        provider: 'mock',
        model_id: 'mock-gemini-pro',
        latency_ms: 100,
      },
      status: 'COMPLETED',
      transcript_snippet: 'Hi, I am booking an apartment in Bangalore...',
      created_at: '2026-10-18T00:00:00Z',
    };

    vi.mocked(coercionApi.analyzeCoercionApi).mockResolvedValueOnce(newAnalysis);

    const onAnalyzed = vi.fn();
    render(<CoercionAnalysisPanel transactionId={transactionId} onAnalyzed={onAnalyzed} />);

    const textarea = screen.getByTestId('coercion-transcript-input');
    fireEvent.change(textarea, {
      target: { value: 'Hi, I am booking an apartment in Bangalore for my daughter college.' },
    });

    const submitBtn = screen.getByTestId('coercion-analyze-button');
    expect(submitBtn).not.toBeDisabled();
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(coercionApi.analyzeCoercionApi).toHaveBeenCalledWith(
        transactionId,
        expect.objectContaining({
          call_transcript: 'Hi, I am booking an apartment in Bangalore for my daughter college.',
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('coercion-level-badge')).toHaveTextContent('NONE');
      expect(screen.getByText(/Mitigating Evidence & Legitimate Explanations/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Customer explicitly books an apartment with verified flat owner./i)
      ).toBeInTheDocument();
    });

    expect(onAnalyzed).toHaveBeenCalled();
  });

  it('shows error banner when analysis API call rejects', async () => {
    vi.mocked(coercionApi.getCoercionLifecycleApi).mockResolvedValueOnce(notStarted);
    vi.mocked(coercionApi.analyzeCoercionApi).mockRejectedValueOnce(
      new Error('Provider timeout during analysis')
    );

    render(<CoercionAnalysisPanel transactionId={transactionId} />);

    const textarea = screen.getByTestId('coercion-transcript-input');
    fireEvent.change(textarea, { target: { value: 'Some call transcript with error' } });

    fireEvent.click(screen.getByTestId('coercion-analyze-button'));

    await waitFor(() => {
      expect(screen.getByTestId('coercion-error-banner')).toBeInTheDocument();
      expect(screen.getByText(/Provider timeout during analysis/i)).toBeInTheDocument();
    });
  });
});

