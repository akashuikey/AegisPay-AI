/**
 * Multi-Turn AI Investigation Conversation Panel.
 * Allows operators to supply customer-provided messages or call transcripts,
 * receive evidence-grounded forensic findings, answer targeted follow-up questions,
 * and iteratively refine the investigation context over bounded turns.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Send,
  Bot,
  User,
  AlertTriangle,
  HelpCircle,
  Clock,
  Sparkles,
  Info,
  RefreshCw,
  Cpu,
} from 'lucide-react';
import {
  ConversationTurnResponse,
  EvidenceProvenance,
  InvestigationConversationResponse,
  getCurrentConversationForTransactionApi,
  startInvestigationConversationApi,
  submitConversationTurnApi,
} from '../api/investigationApi';

interface InvestigationConversationPanelProps {
  transactionId: string;
  transactionRecipient: string;
  transactionAmount: number;
}

export function InvestigationConversationPanel({
  transactionId,
  transactionRecipient,
  transactionAmount,
}: InvestigationConversationPanelProps) {
  const [conversation, setConversation] = useState<InvestigationConversationResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [inputContent, setInputContent] = useState<string>('');
  const [provenance, setProvenance] = useState<EvidenceProvenance>('customer_statement');

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of conversation turns
  const scrollToBottom = () => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation?.turns]);

  // Load active or existing conversation for this transaction
  const loadConversation = useCallback(async () => {
    if (!transactionId || transactionId.startsWith('AST-')) return;
    try {
      setLoading(true);
      setError(null);
      const conv = await getCurrentConversationForTransactionApi(transactionId);
      setConversation(conv);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load conversation';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [transactionId]);

  useEffect(() => {
    void loadConversation();
  }, [loadConversation]);

  // Start new conversation if none exists
  const handleStartConversation = async () => {
    try {
      setSubmitting(true);
      setError(null);
      const conv = await startInvestigationConversationApi(transactionId, {
        initial_message: inputContent.trim() ? inputContent.trim() : undefined,
        evidence_provenance: provenance,
      });
      setConversation(conv);
      setInputContent('');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to start conversation';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  // Submit next turn
  const handleSubmitTurn = async (contentToSend?: string) => {
    const text = contentToSend ?? inputContent.trim();
    if (!text || !conversation || submitting) return;

    try {
      setSubmitting(true);
      setError(null);
      const updated = await submitConversationTurnApi(
        conversation.id,
        {
          content: text,
          evidence_provenance: provenance,
          client_turn_id: `turn_${Date.now()}`,
        },
        transactionId
      );
      setConversation(updated);
      setInputContent('');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to submit conversation turn';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  // Helper for sentiment colors
  const getSentimentTone = (sentiment?: string | null) => {
    switch (sentiment) {
      case 'MALICIOUS':
        return 'red';
      case 'COERCED':
        return 'rose';
      case 'SUSPICIOUS':
        return 'amber';
      case 'BENIGN':
        return 'green';
      default:
        return 'blue';
    }
  };

  // Extract latest follow-up questions
  const latestAssistantTurn = conversation?.turns
    ?.slice()
    ?.reverse()
    ?.find((t) => {
      const r = String(t.role).toUpperCase();
      return r === 'AI_ASSISTANT' || r === 'ASSISTANT';
    });

  const followUpQuestions = latestAssistantTurn?.follow_up_questions ?? [];

  return (
    <section className="drawer-section" data-testid="investigation-conversation-panel">
      {/* Header and status bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 6, margin: 0 }}>
            <Sparkles size={16} color="#d97706" />
            AI Forensic Investigation Dialogue
          </h3>
          <p style={{ margin: '4px 0 0 0', fontSize: 12, color: '#6b7280' }}>
            Multi-turn contextual inquiry with evidence grounding & targeted follow-up prompts
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {conversation && (
            <span
              className="pill mono"
              style={{ fontSize: 11 }}
              data-testid="conversation-turn-counter"
            >
              Turns: {conversation.turn_count}/20
            </span>
          )}
          <button
            className="button small"
            onClick={loadConversation}
            disabled={loading || submitting}
            title="Refresh conversation"
            aria-label="Refresh conversation"
          >
            <RefreshCw size={12} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {/* Non-mutation advisory */}
      <div
        style={{
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: 6,
          padding: '8px 12px',
          fontSize: 12,
          color: '#475569',
          marginBottom: 14,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <Info size={14} color="#0284c7" style={{ flexShrink: 0 }} />
        <span>
          <strong>Forensic Intelligence Only:</strong> This dialogue generates forensic observations. It{' '}
          <em>never mutates transaction workflow state</em> or executes unauthorized payments.
        </span>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            background: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#991b1b',
            borderRadius: 6,
            padding: '10px 12px',
            fontSize: 13,
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
          data-testid="conversation-error-alert"
        >
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {loading && !conversation ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: '#6b7280' }}>
          <RefreshCw size={18} className="spin" style={{ margin: '0 auto 8px auto', display: 'block' }} />
          Loading investigation session…
        </div>
      ) : !conversation ? (
        /* Empty State: No active conversation yet */
        <div
          style={{
            background: '#fafafa',
            border: '1px dashed #cbd5e1',
            borderRadius: 8,
            padding: 20,
            textAlign: 'center',
          }}
          data-testid="conversation-empty-state"
        >
          <Bot size={28} color="#64748b" style={{ margin: '0 auto 8px auto', display: 'block' }} />
          <h4 style={{ margin: '0 0 6px 0', fontSize: 14 }}>No Active Investigation Conversation</h4>
          <p style={{ margin: '0 0 14px 0', fontSize: 12, color: '#64748b' }}>
            Initiate a multi-turn case dialogue for recipient <strong>{transactionRecipient}</strong> (
            ₹{transactionAmount.toLocaleString('en-IN')}).
          </p>
          <div style={{ maxWidth: 450, margin: '0 auto', textAlign: 'left' }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: '#475569', display: 'block', marginBottom: 4 }}>
              Initial note / customer statement (optional):
            </label>
            <textarea
              className="field-input"
              rows={3}
              placeholder="e.g., Customer reports receiving urgent call from alleged CBI officer claiming illegal SIM usage..."
              value={inputContent}
              onChange={(e) => setInputContent(e.target.value)}
              style={{ width: '100%', marginBottom: 10, resize: 'vertical' }}
              data-testid="input-initial-conversation"
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <select
                className="select small"
                value={provenance}
                onChange={(e) => setProvenance(e.target.value as EvidenceProvenance)}
                style={{ maxWidth: 200 }}
              >
                <option value="customer_statement">Customer statement</option>
                <option value="document_extraction">Document extraction</option>
                <option value="device_telephony">Telephony / active call</option>
                <option value="historical_ledger">Historical ledger</option>
              </select>

              <button
                className="button primary small"
                onClick={handleStartConversation}
                disabled={submitting}
                data-testid="button-start-conversation"
              >
                {submitting ? 'Initiating…' : 'Start Investigation Dialogue'}
              </button>
            </div>
          </div>
        </div>
      ) : (
        /* Active Conversation Turns */
        <div>
          <div
            style={{
              maxHeight: 460,
              overflowY: 'auto',
              paddingRight: 6,
              marginBottom: 16,
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
            data-testid="conversation-turn-list"
          >
            {conversation.turns.map((turn: ConversationTurnResponse) => {
              const roleUpper = String(turn.role).toUpperCase();
              const isAssistant = roleUpper === 'AI_ASSISTANT' || roleUpper === 'ASSISTANT';
              const isOperator = roleUpper === 'OPERATOR';
              const provider = (turn.model_metadata?.provider as string) ?? 'mock_gemini';

              return (
                <div
                  key={turn.id}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: isOperator ? 'flex-end' : 'flex-start',
                  }}
                  data-testid={`conversation-turn-${turn.turn_index}`}
                >
                  {/* Turn header meta */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      fontSize: 11,
                      color: '#64748b',
                      marginBottom: 4,
                    }}
                  >
                    {isAssistant ? (
                      <>
                        <Bot size={13} color="#2563eb" />
                        <span style={{ fontWeight: 600, color: '#1e40af' }}>Gemini Forensic Analyst</span>
                        <span className="pill small mono">
                          <Cpu size={10} style={{ marginRight: 3, verticalAlign: 'middle' }} />
                          {provider === 'vertex_ai' ? 'Vertex AI' : 'Offline Mock'}
                        </span>
                      </>
                    ) : (
                      <>
                        <User size={13} color="#475569" />
                        <span style={{ fontWeight: 600 }}>Operator (Turn #{turn.turn_index})</span>
                        {turn.evidence_provenance && (
                          <span className="pill small">{turn.evidence_provenance}</span>
                        )}
                      </>
                    )}
                    <span style={{ marginLeft: 4 }}>
                      <Clock size={10} style={{ marginRight: 2, verticalAlign: 'middle' }} />
                      {new Date(turn.created_at).toLocaleTimeString('en-IN', {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </span>
                  </div>

                  {/* Turn bubble */}
                  <div
                    style={{
                      maxWidth: '90%',
                      background: isAssistant ? '#f8fafc' : '#eff6ff',
                      border: `1px solid ${isAssistant ? '#cbd5e1' : '#bfdbfe'}`,
                      borderRadius: 8,
                      padding: '12px 14px',
                      fontSize: 13,
                      lineHeight: 1.5,
                      color: '#1e293b',
                    }}
                  >
                    <div style={{ whiteSpace: 'pre-wrap' }}>{turn.content}</div>

                    {/* Forensic assessment strip for assistant turns */}
                    {isAssistant && turn.risk_sentiment && (
                      <div
                        style={{
                          marginTop: 10,
                          paddingTop: 8,
                          borderTop: '1px solid #e2e8f0',
                          display: 'flex',
                          flexWrap: 'wrap',
                          gap: 6,
                          alignItems: 'center',
                        }}
                      >
                        <span className={`pill ${getSentimentTone(turn.risk_sentiment)}`}>
                          Risk Sentiment: {turn.risk_sentiment}
                        </span>
                        {turn.confidence && (
                          <span className="pill blue">
                            Confidence: {turn.confidence}
                            {turn.confidence_score != null
                              ? ` (${(turn.confidence_score * 100).toFixed(0)}%)`
                              : ''}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Findings list if present */}
                    {isAssistant && turn.findings && turn.findings.length > 0 && (
                      <div style={{ marginTop: 10 }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 4 }}>
                          SUPPORTING FORENSIC FINDINGS:
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {turn.findings.map((f) => (
                            <div
                              key={f.id}
                              style={{
                                background: '#ffffff',
                                border: '1px solid #e2e8f0',
                                borderRadius: 4,
                                padding: '6px 8px',
                                fontSize: 12,
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <strong style={{ color: '#0f172a' }}>{f.category}</strong>
                                <span className={`pill small ${f.severity === 'CRITICAL' ? 'red' : 'amber'}`}>
                                  {f.severity}
                                </span>
                              </div>
                              <p style={{ margin: '3px 0 0 0', color: '#334155' }}>{f.explanation}</p>
                              {f.supporting_evidence_references.length > 0 && (
                                <div style={{ marginTop: 4, fontSize: 10, color: '#64748b' }}>
                                  Evidence: {f.supporting_evidence_references.join(', ')}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Missing information alerts */}
                    {isAssistant && turn.missing_information && turn.missing_information.length > 0 && (
                      <div
                        style={{
                          marginTop: 8,
                          padding: '6px 8px',
                          background: '#fffbeb',
                          border: '1px solid #fef3c7',
                          borderRadius: 4,
                          fontSize: 11,
                          color: '#92400e',
                        }}
                      >
                        <strong>Missing Context:</strong> {turn.missing_information.join('; ')}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Follow-up Question Suggestion Chips */}
          {followUpQuestions.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: '#475569',
                  marginBottom: 6,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                <HelpCircle size={12} color="#0284c7" />
                TARGETED INQUIRY PROMPTS (Click to answer):
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {followUpQuestions.map((q, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="button small"
                    style={{
                      textAlign: 'left',
                      fontSize: 11,
                      background: '#f0fdf4',
                      borderColor: '#bbf7d0',
                      color: '#166534',
                      cursor: 'pointer',
                    }}
                    onClick={() => {
                      setInputContent(`Customer answer to "${q}": `);
                    }}
                    data-testid={`chip-follow-up-${idx}`}
                  >
                    + {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Operator Turn Composer */}
          <div
            style={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              padding: 12,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#334155' }}>
                Add Operator Note / Customer Evidence:
              </label>
              <select
                className="select small"
                value={provenance}
                onChange={(e) => setProvenance(e.target.value as EvidenceProvenance)}
                style={{ fontSize: 11, padding: '2px 6px' }}
                aria-label="Evidence provenance source"
              >
                <option value="customer_statement">Customer statement</option>
                <option value="document_extraction">Document extraction</option>
                <option value="device_telephony">Telephony / call telemetry</option>
                <option value="historical_ledger">Historical ledger</option>
              </select>
            </div>

            <textarea
              className="field-input"
              rows={3}
              placeholder="Type customer statements, follow-up answers, or forensic notes..."
              value={inputContent}
              onChange={(e) => setInputContent(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  void handleSubmitTurn();
                }
              }}
              style={{ width: '100%', marginBottom: 8, resize: 'vertical' }}
              disabled={submitting}
              data-testid="input-conversation-turn"
            />

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: '#94a3b8' }}>Ctrl+Enter or Cmd+Enter to send</span>
              <button
                className="button primary small"
                onClick={() => handleSubmitTurn()}
                disabled={submitting || !inputContent.trim()}
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                data-testid="button-send-conversation-turn"
              >
                {submitting ? (
                  <>
                    <RefreshCw size={12} className="spin" />
                    Analyzing…
                  </>
                ) : (
                  <>
                    <Send size={12} />
                    Submit Turn
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
