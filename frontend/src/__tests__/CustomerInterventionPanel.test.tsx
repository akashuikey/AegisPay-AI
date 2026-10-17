import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { CustomerInterventionPanel } from '../components/CustomerInterventionPanel';
import * as responseApi from '../api/responseApi';
import type { FraudResponseDetails } from '../api/responseApi';

function makeResponse(overrides: Partial<FraudResponseDetails> = {}): FraudResponseDetails {
  return {
    id: 'resp-1',
    transaction_id: 'tx-1',
    decision_id: 'dec-1',
    response_type: 'ALLOW_SETTLED',
    action: 'ALLOW',
    processing_status: 'COMPLETED',
    from_state: 'DECISION_READY',
    to_state: 'SETTLED_SIMULATED',
    headline: 'Payment Approved and Settled',
    customer_message:
      'Your payment of ₹1,500.00 to Priya Sharma has been approved and processed through Aster Bank simulated rails.',
    customer_action_required: 'NONE',
    next_steps: [
      'Your account statement has been updated.',
      'No further action is required.',
    ],
    idempotency_key: null,
    created_at: '2026-10-18T10:00:00Z',
    notifications: [
      {
        id: 'notif-1',
        channel: 'IN_APP_SIMULATED',
        recipient_masked: 'p***a@upi',
        subject: 'Aster Bank Safety Alert: Payment Approved',
        message_body: 'Your payment of ₹1,500.00 to Priya Sharma has been approved.',
        delivery_status: 'DELIVERED_SIMULATED',
        failure_reason: null,
        created_at: '2026-10-18T10:00:01Z',
        delivered_at: '2026-10-18T10:00:01Z',
      },
    ],
    is_simulated: true,
    ...overrides,
  };
}

describe('CustomerInterventionPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders placeholder when no automated response exists yet', async () => {
    vi.spyOn(responseApi, 'getLatestResponseApi').mockResolvedValue(null);
    render(<CustomerInterventionPanel transactionId="tx-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('no-response-placeholder')).toBeInTheDocument();
    });
    expect(screen.getByTestId('button-execute-response')).toHaveTextContent('Execute Automated Response');
    expect(screen.getByTestId('simulated-response-disclaimer')).toBeInTheDocument();
  });

  it('loads and renders existing automated response and intervention details', async () => {
    vi.spyOn(responseApi, 'getLatestResponseApi').mockResolvedValue(
      makeResponse({
        response_type: 'HOLD_PROTECTIVE',
        action: 'HOLD_FOR_INVESTIGATION',
        headline: 'Temporary Pre-Settlement Hold',
        customer_action_required: 'CONTACT_BANK',
        next_steps: [
          'Hang up any active voice calls immediately.',
          'Aster Bank will never ask for your PIN.',
        ],
      })
    );

    render(<CustomerInterventionPanel transactionId="tx-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('customer-intervention-card')).toBeInTheDocument();
    });

    expect(screen.getByText('Temporary Pre-Settlement Hold')).toBeInTheDocument();
    expect(screen.getByTestId('customer-action-badge')).toHaveTextContent('Contact Bank Official Channels');
    expect(screen.getByTestId('customer-next-steps')).toHaveTextContent('Hang up any active voice calls immediately.');
    expect(screen.getByTestId('notification-delivery-card')).toBeInTheDocument();
    expect(screen.getByTestId('notification-status-badge')).toHaveTextContent('DELIVERED_SIMULATED');
    expect(screen.getByTestId('notification-recipient')).toHaveTextContent('p***a@upi');
  });

  it('executes automated response on operator click and updates UI', async () => {
    vi.spyOn(responseApi, 'getLatestResponseApi').mockResolvedValue(null);
    const executeSpy = vi.spyOn(responseApi, 'executeResponseApi').mockResolvedValue(
      makeResponse({
        response_type: 'VERIFICATION_REQUIRED',
        action: 'REQUIRE_VERIFICATION',
        headline: 'Additional Verification Required',
        customer_action_required: 'VERIFY_OTP',
      })
    );

    const onExecuted = vi.fn();
    render(<CustomerInterventionPanel transactionId="tx-1" onResponseExecuted={onExecuted} />);

    await waitFor(() => {
      expect(screen.getByTestId('button-execute-response')).toBeInTheDocument();
    });

    // Change channel
    fireEvent.change(screen.getByTestId('select-notification-channel'), {
      target: { value: 'SMS_SIMULATED' },
    });

    fireEvent.click(screen.getByTestId('button-execute-response'));

    await waitFor(() => {
      expect(executeSpy).toHaveBeenCalledWith('tx-1', {
        channel: 'SMS_SIMULATED',
        simulate_notification_failure: false,
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('customer-intervention-card')).toBeInTheDocument();
    });
    expect(screen.getByText('Additional Verification Required')).toBeInTheDocument();
    expect(onExecuted).toHaveBeenCalledTimes(1);
  });

  it('handles simulated notification failure isolation', async () => {
    vi.spyOn(responseApi, 'getLatestResponseApi').mockResolvedValue(null);
    const executeSpy = vi.spyOn(responseApi, 'executeResponseApi').mockResolvedValue(
      makeResponse({
        response_type: 'BLOCK_SAFETY',
        action: 'BLOCK',
        headline: 'Transfer Could Not Be Completed',
        notifications: [
          {
            id: 'notif-2',
            channel: 'EMAIL_SIMULATED',
            recipient_masked: 'u***r@bank.in',
            message_body: 'Your transfer could not be completed.',
            delivery_status: 'FAILED_SIMULATED',
            failure_reason: 'SIMULATED_CARRIER_TIMEOUT',
            created_at: '2026-10-18T10:00:00Z',
          },
        ],
      })
    );

    render(<CustomerInterventionPanel transactionId="tx-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('button-execute-response')).toBeInTheDocument();
    });

    // Check simulate failure checkbox
    fireEvent.click(screen.getByTestId('checkbox-simulate-failure'));

    fireEvent.click(screen.getByTestId('button-execute-response'));

    await waitFor(() => {
      expect(executeSpy).toHaveBeenCalledWith('tx-1', {
        channel: 'IN_APP_SIMULATED',
        simulate_notification_failure: true,
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('notification-failure-reason')).toBeInTheDocument();
    });
    expect(screen.getByTestId('notification-failure-reason')).toHaveTextContent('SIMULATED_CARRIER_TIMEOUT');
    expect(screen.getByTestId('notification-status-badge')).toHaveTextContent('FAILED_SIMULATED');
  });

  it('displays error notice when API call fails', async () => {
    vi.spyOn(responseApi, 'getLatestResponseApi').mockRejectedValue(new Error('Network error'));
    render(<CustomerInterventionPanel transactionId="tx-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('response-error-notice')).toBeInTheDocument();
    });
    expect(screen.getByTestId('response-error-notice')).toHaveTextContent('Network error');
  });
});

