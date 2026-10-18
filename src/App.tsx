import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  Cpu,
  CreditCard,
  Download,
  Mic,
  MicOff,
  Network,
  PhoneCall,
  PhoneIncoming,
  PhoneOff,
  Play,
  Pause,
  Search,
  Send,
  Share2,
  Shield,
  ShieldAlert,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  User,
  Users,
  X,
} from 'lucide-react';
import { RECIPIENT_REGISTRY, resolveRecipient, FictionalRecipient } from './domain/recipientRegistry';
import { evaluateRiskLocally, RiskAssessmentResponse, SCENARIO_CATALOG } from './api/riskApi';
import { AudioTranscribeModal } from './components/AudioTranscribeModal';
import ScenarioSimulationPanel from './components/ScenarioSimulationPanel';

// ---------------------------------------------------------------------------
// Types & State Definitions
// ---------------------------------------------------------------------------

type NavTab = 'Live System' | 'Scenarios' | 'Analytics' | 'Audit Logs';

interface UserPaymentItem {
  id: string;
  userNum: number;
  userName: string;
  initials: string;
  recipientName: string;
  recipientUpi: string;
  amount: number;
  checkReason: string;
  initiatedOn: string;
  riskScore: number;
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  verificationStatus: 'Pending' | 'In Progress' | 'Verified' | 'Hold' | 'Cancelled';
  purpose: string;
  hasCoercion: boolean;
  transcriptEntries: Array<{
    speaker: string;
    role: 'caller' | 'user' | 'officer';
    time: string;
    text: string;
    threatBadge?: string;
    threatTone?: 'danger' | 'warning' | 'info';
  }>;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('Live System');
  const [searchQuery, setSearchQuery] = useState('');
  const [isTranscribeModalOpen, setIsTranscribeModalOpen] = useState(false);

  // Audio Playback State for Waveform Bar
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);

  // Live Investigation Tab State
  const [investigationTab, setInvestigationTab] = useState<'Transcript' | 'Conversation' | 'AI Analysis'>('Transcript');

  // Customer Mobile Payment & Call Screen State
  const [mobileViewMode, setMobileViewMode] = useState<'send_money' | 'call'>('send_money');
  const [mobileUpi, setMobileUpi] = useState('rohit@upi');
  const [mobileAmount, setMobileAmount] = useState('250000');
  const [mobilePurpose, setMobilePurpose] = useState('Payment for official fees');
  const [mobileCallActive, setMobileCallActive] = useState(false);
  const [mobileCallStatus, setMobileCallStatus] = useState<'RINGING' | 'CONNECTED' | 'ENDED'>('RINGING');
  const [callDuration, setCallDuration] = useState(0);
  const [mobilePaymentHeld, setMobilePaymentHeld] = useState(false);
  const [isAnalyzingPay, setIsAnalyzingPay] = useState(false);

  // Live Conversation Messages with Gemini AI inside the phone
  const [conversationMessages, setConversationMessages] = useState<Array<{ role: 'officer' | 'customer'; text: string; time: string }>>([
    {
      role: 'officer',
      text: 'Hello, this is AegisPay Fraud Prevention. Can you confirm if anyone asked you to stay on this line while transferring money?',
      time: '10:24:16 AM',
    },
  ]);
  const [customerPhoneInput, setCustomerPhoneInput] = useState('');
  const [isGeminiReplying, setIsGeminiReplying] = useState(false);

  // Call duration timer
  useEffect(() => {
    let timer: any;
    if (mobileCallActive && mobileCallStatus === 'CONNECTED') {
      timer = setInterval(() => {
        setCallDuration((prev) => prev + 1);
      }, 1000);
    } else {
      setCallDuration(0);
    }
    return () => clearInterval(timer);
  }, [mobileCallActive, mobileCallStatus]);

  // Initial Seeded Users matching Reference Screenshot
  const [userList, setUserList] = useState<UserPaymentItem[]>([
    {
      id: 'tx_user_1',
      userNum: 1,
      userName: 'John Doe',
      initials: 'JD',
      recipientName: 'Rohit Sharma (UPI)',
      recipientUpi: 'rohit@upi',
      amount: 250000,
      checkReason: 'Unusual payment pattern',
      initiatedOn: 'Today, 10:24 AM',
      riskScore: 82,
      riskLevel: 'CRITICAL',
      verificationStatus: 'Pending',
      purpose: 'Payment for official fees',
      hasCoercion: true,
      transcriptEntries: [
        {
          speaker: 'Caller (Unknown)',
          role: 'caller',
          time: '10:24:05 AM',
          text: 'This is the police department. You need to transfer the amount immediately or you will be arrested.',
          threatBadge: 'Authority Impersonation',
          threatTone: 'danger',
        },
        {
          speaker: 'User',
          role: 'user',
          time: '10:24:12 AM',
          text: "I'm scared. What should I do?",
          threatBadge: 'Signs of Coercion',
          threatTone: 'warning',
        },
        {
          speaker: 'Caller (Unknown)',
          role: 'caller',
          time: '10:24:18 AM',
          text: 'Do not tell anyone. Just complete the payment now.',
          threatBadge: 'Secrecy Instruction',
          threatTone: 'danger',
        },
      ],
    },
    {
      id: 'tx_user_2',
      userNum: 2,
      userName: 'Sneha Kapoor',
      initials: 'SK',
      recipientName: 'Investment Account',
      recipientUpi: 'apexyield@icici',
      amount: 85000,
      checkReason: 'First-time beneficiary',
      initiatedOn: 'Today, 10:18 AM',
      riskScore: 65,
      riskLevel: 'HIGH',
      verificationStatus: 'In Progress',
      purpose: 'Crypto trading deposit',
      hasCoercion: true,
      transcriptEntries: [
        {
          speaker: 'Telegram Admin',
          role: 'caller',
          time: '10:17:40 AM',
          text: 'Guaranteed 25% daily return. Transfer now to lock your allocation and tell your bank this is for family.',
          threatBadge: 'Guaranteed Return Claim',
          threatTone: 'danger',
        },
        {
          speaker: 'User',
          role: 'user',
          time: '10:18:02 AM',
          text: 'Is there any risk involved in this?',
          threatBadge: 'High-Yield Trap',
          threatTone: 'warning',
        },
      ],
    },
    {
      id: 'tx_user_3',
      userNum: 3,
      userName: 'Arjun Rao',
      initials: 'AR',
      recipientName: 'Electricity Provider',
      recipientUpi: 'electricity@bescom',
      amount: 3450,
      checkReason: 'Routine bill payment',
      initiatedOn: 'Today, 09:52 AM',
      riskScore: 8,
      riskLevel: 'LOW',
      verificationStatus: 'Verified',
      purpose: 'Monthly electricity bill',
      hasCoercion: false,
      transcriptEntries: [
        {
          speaker: 'User',
          role: 'user',
          time: '09:52:10 AM',
          text: 'Paying my monthly electricity bill to BESCOM.',
          threatBadge: 'Legitimate Context',
          threatTone: 'info',
        },
      ],
    },
  ]);

  const [selectedUserId, setSelectedUserId] = useState<string>('tx_user_1');

  const selectedUser = useMemo(() => {
    return userList.find((u) => u.id === selectedUserId) || userList[0];
  }, [userList, selectedUserId]);

  // Selected Demo Scenario
  const [selectedScenarioKey, setSelectedScenarioKey] = useState<string>('digital_arrest');

  const scenarioRadioOptions = [
    { key: 'digital_arrest', label: 'Digital Arrest Scam', risk: 'High Risk', tone: 'high' },
    { key: 'investment_scam', label: 'Investment Fraud', risk: 'High Risk', tone: 'high' },
    { key: 'fake_invoice', label: 'Fake Invoice', risk: 'High Risk', tone: 'high' },
    { key: 'mule_network', label: 'Mule Account', risk: 'Medium Risk', tone: 'medium' },
    { key: 'legitimate_high_value', label: 'Legitimate High-Value Transfer', risk: 'Low Risk', tone: 'low' },
    { key: 'ambiguous_payment', label: 'Ambiguous Payment', risk: 'Medium Risk', tone: 'medium' },
    { key: 'ordinary_stressed_customer', label: 'Ordinary Stressed Customer', risk: 'Medium Risk', tone: 'medium' },
    { key: 'strong_coercion_after_verification', label: 'Strong Coercion After Verification', risk: 'High Risk', tone: 'high' },
  ];

  // Filtered users for left panel
  const filteredUsers = useMemo(() => {
    if (!searchQuery.trim()) return userList;
    const q = searchQuery.toLowerCase();
    return userList.filter(
      (u) =>
        u.userName.toLowerCase().includes(q) ||
        u.recipientName.toLowerCase().includes(q) ||
        u.recipientUpi.toLowerCase().includes(q)
    );
  }, [userList, searchQuery]);

  // Audio Playback Simulator
  useEffect(() => {
    let interval: any;
    if (isPlayingAudio) {
      interval = setInterval(() => {
        setAudioProgress((prev) => {
          if (prev >= 28) {
            setIsPlayingAudio(false);
            return 0;
          }
          return prev + 1;
        });
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isPlayingAudio]);

  // Run Scenario Trigger
  const handleRunScenario = (scenarioKey: string) => {
    setSelectedScenarioKey(scenarioKey);
    const catalogItem = SCENARIO_CATALOG[scenarioKey] || SCENARIO_CATALOG.digital_arrest;

    // Populate mobile preview form
    setMobileUpi(catalogItem.recipientIdentifier || 'rohit@upi');
    setMobileAmount(String(catalogItem.amount));
    setMobilePurpose(catalogItem.purpose || 'Payment for official fees');

    // Deterministic risk evaluation
    const evalResult = evaluateRiskLocally(catalogItem.evidence);

    const newTx: UserPaymentItem = {
      id: `tx_${Date.now()}`,
      userNum: userList.length + 1,
      userName: catalogItem.label.replace(/^\d+\.\s*/, '') || 'Simulated User',
      initials: 'SU',
      recipientName: catalogItem.recipient || 'Rohit Sharma (UPI)',
      recipientUpi: catalogItem.recipientIdentifier || 'rohit@upi',
      amount: catalogItem.amount,
      checkReason: catalogItem.summary || 'Scenario execution test',
      initiatedOn: 'Just now',
      riskScore: evalResult.risk_score,
      riskLevel: evalResult.risk_level,
      verificationStatus: evalResult.recommended_action === 'HOLD_FOR_INVESTIGATION' ? 'Hold' : 'In Progress',
      purpose: catalogItem.purpose || 'Payment',
      hasCoercion: evalResult.risk_score >= 60,
      transcriptEntries: [
        {
          speaker: 'Caller (Unknown)',
          role: 'caller',
          time: 'Just now',
          text: catalogItem.summary || 'Immediate fund transfer requested.',
          threatBadge: evalResult.triggered_rules[0]?.rule_name || 'High Risk Indicator',
          threatTone: 'danger',
        },
        {
          speaker: 'User',
          role: 'user',
          time: 'Just now',
          text: 'I am completing the transaction now.',
          threatBadge: 'Urgency Pressure',
          threatTone: 'warning',
        },
      ],
    };

    setUserList((prev) => [newTx, ...prev]);
    setSelectedUserId(newTx.id);

    // Reset phone call states
    setMobileCallActive(false);
    setMobilePaymentHeld(false);
    setMobileViewMode('send_money');
  };

  // Pay Now Handler from Mobile Preview
  const handleMobilePayNow = () => {
    setIsAnalyzingPay(true);
    setTimeout(() => {
      setIsAnalyzingPay(false);
      // High-risk transaction triggers the live security phone call!
      setMobileCallActive(true);
      setMobileCallStatus('RINGING');
      setMobileViewMode('call');
    }, 800);
  };

  // Accept incoming phone call inside the mobile phone!
  const handleAcceptCall = () => {
    setMobileCallActive(true);
    setMobileCallStatus('CONNECTED');
    setMobileViewMode('call');
    if (conversationMessages.length === 0) {
      setConversationMessages([
        {
          role: 'officer',
          text: 'Hello, this is AegisPay Fraud Prevention. Can you confirm if anyone asked you to stay on this line while transferring money?',
          time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        },
      ]);
    }
  };

  // Decline incoming phone call
  const handleDeclineCall = () => {
    setMobileCallActive(false);
    setMobileCallStatus('ENDED');
    setMobilePaymentHeld(true);
    setMobileViewMode('send_money');
  };

  // End active phone call
  const handleEndCall = () => {
    setMobileCallActive(false);
    setMobileCallStatus('ENDED');
    setMobilePaymentHeld(true);
    setMobileViewMode('send_money');
  };

  // Send conversation message to Gemini AI inside the phone
  const handleSendPhoneMessage = async (msgText: string) => {
    if (!msgText.trim()) return;

    const userMsg = {
      role: 'customer' as const,
      text: msgText,
      time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    };

    setConversationMessages((prev) => [...prev, userMsg]);
    setCustomerPhoneInput('');
    setIsGeminiReplying(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: msgText,
          context: `You are AegisPay Fraud Prevention Officer speaking directly with the user on phone. User is transferring ₹${mobileAmount} to ${mobileUpi}. Risk Score: ${selectedUser.riskScore}/100. Be calm, reassuring, and guide them away from scammers.`,
        }),
      });
      const data = await res.json();
      const officerReply = {
        role: 'officer' as const,
        text: data.reply || 'Please stay calm. AegisPay has temporarily paused this payment. Real police and government officials will NEVER demand money transfers or threaten you over WhatsApp or phone calls.',
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      };
      setConversationMessages((prev) => [...prev, officerReply]);
    } catch {
      const officerReply = {
        role: 'officer' as const,
        text: 'Please remain calm. AegisPay has placed a safe protective hold on your transfer. Legitimate government authorities and courts never conduct digital arrests or demand money transfers over the phone.',
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      };
      setConversationMessages((prev) => [...prev, officerReply]);
    } finally {
      setIsGeminiReplying(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: '#edf1f4', display: 'flex', flexDirection: 'column' }}>
      {/* --------------------------------------------------------------------- */}
      {/* Top Header matching Reference Screenshot */}
      {/* --------------------------------------------------------------------- */}
      <header className="aegis-header">
        <div className="aegis-logo">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <path d="M14 3L3 23H9.5L14 14.5L18.5 23H25L14 3Z" fill="url(#aegis-grad-logo)" />
            <defs>
              <linearGradient id="aegis-grad-logo" x1="3" y1="3" x2="25" y2="23" gradientUnits="userSpaceOnUse">
                <stop stopColor="#0284c7" />
                <stop offset="1" stopColor="#0d9488" />
              </linearGradient>
            </defs>
          </svg>
          <span style={{ fontWeight: 800, fontSize: 18, color: '#0f172a', letterSpacing: '-0.3px' }}>AegisPay AI</span>
        </div>

        <nav className="aegis-nav-tabs">
          <button
            type="button"
            className={`aegis-nav-tab ${activeTab === 'Live System' ? 'active' : ''}`}
            onClick={() => setActiveTab('Live System')}
          >
            Live System
          </button>
          <button
            type="button"
            className={`aegis-nav-tab ${activeTab === 'Scenarios' ? 'active' : ''}`}
            onClick={() => setActiveTab('Scenarios')}
          >
            Scenarios
          </button>
          <button
            type="button"
            className={`aegis-nav-tab ${activeTab === 'Analytics' ? 'active' : ''}`}
            onClick={() => setActiveTab('Analytics')}
          >
            Analytics
          </button>
          <button
            type="button"
            className={`aegis-nav-tab ${activeTab === 'Audit Logs' ? 'active' : ''}`}
            onClick={() => setActiveTab('Audit Logs')}
          >
            Audit Logs
          </button>
        </nav>

        <div className="aegis-header-actions" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            className="system-live-pill"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 7,
              background: '#ecfdf5',
              color: '#065f46',
              border: '1px solid #d1fae5',
              borderRadius: 20,
              padding: '5px 14px',
              fontSize: 11.5,
              fontWeight: 700,
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: '#10b981',
                boxShadow: '0 0 0 3px rgba(16, 185, 129, 0.2)',
              }}
            />
            System Live
          </div>

          <div
            className="user-avatar-badge"
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: '#1e3a8a',
              color: '#ffffff',
              display: 'grid',
              placeItems: 'center',
              fontSize: 12,
              fontWeight: 700,
              boxShadow: '0 2px 6px rgba(30, 58, 138, 0.25)',
              cursor: 'default',
            }}
            title="Aegis Operations Operator"
          >
            A
          </div>
        </div>
      </header>

      {/* --------------------------------------------------------------------- */}
      {/* Body Views */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === 'Scenarios' ? (
        <main style={{ padding: '24px 30px', flex: 1 }}>
          <ScenarioSimulationPanel />
        </main>
      ) : activeTab === 'Analytics' ? (
        <main style={{ padding: '24px 30px', flex: 1 }}>
          <div className="aegis-card">
            <h2 className="aegis-card-title">Fraud Prevention Analytics & Risk Trends</h2>
            <p className="aegis-card-subtitle">Real-time statistics across all registered accounts</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginTop: 16 }}>
              <div style={{ padding: 16, background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: 11, color: '#64748b' }}>Mean Investigation Latency</div>
                <div style={{ fontSize: 24, fontWeight: 800, color: '#0f172a', margin: '6px 0' }}>85 ms</div>
                <div style={{ fontSize: 11, color: '#16a34a' }}>Deterministic Engine</div>
              </div>
              <div style={{ padding: 16, background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: 11, color: '#64748b' }}>Coercion Interceptions</div>
                <div style={{ fontSize: 24, fontWeight: 800, color: '#b91c1c', margin: '6px 0' }}>14 Cases</div>
                <div style={{ fontSize: 11, color: '#b91c1c' }}>100% Funds Saved</div>
              </div>
              <div style={{ padding: 16, background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: 11, color: '#64748b' }}>False Positive Rate</div>
                <div style={{ fontSize: 24, fontWeight: 800, color: '#0f766e', margin: '6px 0' }}>0.04%</div>
                <div style={{ fontSize: 11, color: '#16a34a' }}>Trusted mitigation active</div>
              </div>
              <div style={{ padding: 16, background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: 11, color: '#64748b' }}>Live Gemini Voice Model</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: '#0284c7', margin: '6px 0' }}>gemini-3.8-live</div>
                <div style={{ fontSize: 11, color: '#0369a1' }}>Live API Resilient</div>
              </div>
            </div>
          </div>
        </main>
      ) : activeTab === 'Audit Logs' ? (
        <main style={{ padding: '24px 30px', flex: 1 }}>
          <div className="aegis-card">
            <h2 className="aegis-card-title">Compliance & Decision Audit Logs</h2>
            <p className="aegis-card-subtitle">Permanent trace of all deterministic rule firings and AI interventions</p>
            <div style={{ overflowX: 'auto', marginTop: 16 }}>
              <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Timestamp</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Tx ID</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Recipient VPA</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Risk Score</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Decision Action</th>
                    <th style={{ padding: '10px 14px', textAlign: 'left' }}>Policy Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {userList.map((u) => (
                    <tr key={u.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '12px 14px', fontFamily: 'monospace', color: '#64748b' }}>{u.initiatedOn}</td>
                      <td style={{ padding: '12px 14px', fontWeight: 600 }}>{u.id}</td>
                      <td style={{ padding: '12px 14px', fontFamily: 'monospace' }}>{u.recipientUpi}</td>
                      <td style={{ padding: '12px 14px' }}>
                        <span className={`score-badge-pill ${u.riskScore >= 80 ? 'high' : u.riskScore >= 40 ? 'medium' : 'low'}`}>
                          {u.riskScore} / 100
                        </span>
                      </td>
                      <td style={{ padding: '12px 14px', fontWeight: 700 }}>
                        {u.riskScore >= 80 ? 'HOLD_PROTECTIVE' : u.riskScore >= 40 ? 'REQUIRE_VERIFICATION' : 'ALLOW_SETTLED'}
                      </td>
                      <td style={{ padding: '12px 14px', color: '#475569' }}>{u.checkReason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      ) : (
        /* ------------------------------------------------------------------- */
        /* Main Command Center matching Reference Screenshot EXACTLY */
        /* ------------------------------------------------------------------- */
        <main className="dashboard-canvas">
          {/* ================================================================= */}
          {/* Column 1 (Left): Users & Payment Activity */}
          {/* ================================================================= */}
          <div className="aegis-card" style={{ height: 'fit-content' }}>
            <div className="aegis-card-title">
              <span>Users & Payment Activity</span>
              <Search size={16} color="#64748b" />
            </div>

            <div className="user-activity-list">
              {filteredUsers.map((item) => {
                const isSelected = item.id === selectedUserId;
                const scoreClass = item.riskScore >= 80 ? 'high' : item.riskScore >= 40 ? 'medium' : 'low';
                const statusClass =
                  item.verificationStatus === 'Verified'
                    ? 'verified'
                    : item.verificationStatus === 'In Progress'
                    ? 'in-progress'
                    : 'pending';

                return (
                  <div
                    key={item.id}
                    className={`user-activity-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedUserId(item.id);
                      setMobileUpi(item.recipientUpi);
                      setMobileAmount(String(item.amount));
                      setMobilePurpose(item.purpose);
                    }}
                  >
                    <div className="user-card-head">
                      <div className="user-profile-left">
                        <div
                          className="user-initials-badge"
                          style={{
                            background: isSelected ? '#dbeafe' : item.userNum === 2 ? '#ede9fe' : '#dcfce7',
                            color: isSelected ? '#1e40af' : item.userNum === 2 ? '#6b21a8' : '#166534',
                          }}
                        >
                          {item.initials}
                        </div>
                        <div>
                          <div className="user-card-name">User {item.userNum}</div>
                          <div className="user-card-id">{item.userName}</div>
                        </div>
                      </div>
                      <ChevronRight size={16} color={isSelected ? '#0284c7' : '#94a3b8'} />
                    </div>

                    <div className="user-data-row">
                      <span className="user-data-label">Recipient</span>
                      <span className="user-data-value">{item.recipientName}</span>
                    </div>
                    <div className="user-data-row">
                      <span className="user-data-label">Amount</span>
                      <span className="user-data-value">₹ {item.amount.toLocaleString('en-IN')}</span>
                    </div>
                    <div className="user-data-row">
                      <span className="user-data-label">Check Reason</span>
                      <span className="user-data-value" style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.checkReason}
                      </span>
                    </div>
                    <div className="user-data-row">
                      <span className="user-data-label">Initiated On</span>
                      <span className="user-data-value">{item.initiatedOn}</span>
                    </div>
                    <div className="user-data-row" style={{ alignItems: 'center' }}>
                      <span className="user-data-label">Risk Score</span>
                      <span className={`score-badge-pill ${scoreClass}`}>{item.riskScore < 10 ? `0${item.riskScore}` : item.riskScore} / 100</span>
                    </div>
                    <div className="user-data-row" style={{ alignItems: 'center' }}>
                      <span className="user-data-label">Verification</span>
                      <span className={`status-badge-pill ${statusClass}`}>{item.verificationStatus}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ================================================================= */}
          {/* Column 2 (Center): Stack of Top Split & Bottom Investigation */}
          {/* ================================================================= */}
          <div className="center-dashboard-stack">
            {/* Center Top Split: Aegis Intelligence (Left) + Payment Summary (Right) */}
            <div className="center-top-split">
              {/* Card 1: Aegis Intelligence Radar Visualization */}
              <div className="aegis-card" style={{ display: 'flex', flexDirection: 'column' }}>
                <div className="aegis-card-title">
                  <span>Aegis Intelligence</span>
                </div>
                <div className="aegis-card-subtitle">Live Fraud Investigation</div>

                <div className="intelligence-hub-box" style={{ flex: 1, minHeight: 275 }}>
                  {/* Subtle Background Connecting SVG */}
                  <svg
                    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
                    viewBox="0 0 460 260"
                    fill="none"
                  >
                    {/* Concentric rings */}
                    <circle cx="230" cy="130" r="78" stroke="#38bdf8" strokeWidth="1.2" strokeDasharray="3 3" opacity="0.65" />
                    <circle cx="230" cy="130" r="60" stroke="#0ea5e9" strokeWidth="1.2" opacity="0.45" />

                    {/* Dotted connecting curves */}
                    <path d="M 125 55 C 165 55, 185 105, 205 118" stroke="#38bdf8" strokeWidth="1.4" strokeDasharray="3 3" opacity="0.8" />
                    <circle cx="125" cy="55" r="3.5" fill="#0284c7" />

                    <path d="M 335 55 C 295 55, 275 105, 255 118" stroke="#38bdf8" strokeWidth="1.4" strokeDasharray="3 3" opacity="0.8" />
                    <circle cx="335" cy="55" r="3.5" fill="#0284c7" />

                    <path d="M 125 205 C 165 205, 185 155, 205 142" stroke="#38bdf8" strokeWidth="1.4" strokeDasharray="3 3" opacity="0.8" />
                    <circle cx="125" cy="205" r="3.5" fill="#0284c7" />

                    <path d="M 335 205 C 295 205, 275 155, 255 142" stroke="#38bdf8" strokeWidth="1.4" strokeDasharray="3 3" opacity="0.8" />
                    <circle cx="335" cy="205" r="3.5" fill="#0284c7" />
                  </svg>

                  {/* 4 Connected Orbital Nodes */}
                  <div className="hub-node-card top-left">
                    <div className="hub-node-title">
                      <div style={{ width: 20, height: 20, borderRadius: 5, background: '#f0fdfa', display: 'grid', placeItems: 'center', border: '1px solid #ccfbf1' }}>
                        <CreditCard size={11} color="#0d9488" />
                      </div>
                      <span>Payment Analysis</span>
                    </div>
                    <div className="hub-node-desc">Analyzing amount, recipient and history</div>
                  </div>

                  <div className="hub-node-card top-right">
                    <div className="hub-node-title">
                      <div style={{ width: 20, height: 20, borderRadius: 5, background: '#f0fdfa', display: 'grid', placeItems: 'center', border: '1px solid #ccfbf1' }}>
                        <BarChart3 size={11} color="#0d9488" />
                      </div>
                      <span>Risk Detection</span>
                    </div>
                    <div className="hub-node-desc">Checking for fraud signals and patterns</div>
                  </div>

                  <div className="hub-node-card bottom-left">
                    <div className="hub-node-title">
                      <div style={{ width: 20, height: 20, borderRadius: 5, background: '#f0fdfa', display: 'grid', placeItems: 'center', border: '1px solid #ccfbf1' }}>
                        <User size={11} color="#0d9488" />
                      </div>
                      <span>Identity Verification</span>
                    </div>
                    <div className="hub-node-desc">Verifying user, device and location</div>
                  </div>

                  <div className="hub-node-card bottom-right">
                    <div className="hub-node-title">
                      <div style={{ width: 20, height: 20, borderRadius: 5, background: '#f0fdfa', display: 'grid', placeItems: 'center', border: '1px solid #ccfbf1' }}>
                        <Share2 size={11} color="#0d9488" />
                      </div>
                      <span>Behaviour Analysis</span>
                    </div>
                    <div className="hub-node-desc">Analyzing recent activity and intent</div>
                  </div>

                  {/* Center Core Badge */}
                  <div className="hub-center-badge">
                    <div style={{ width: 34, height: 34, borderRadius: '50%', background: '#f0fdfa', display: 'grid', placeItems: 'center', border: '1.5px solid #38bdf8' }}>
                      <ShieldCheck size={20} color="#0284c7" />
                    </div>
                    <div style={{ fontSize: 10.5, fontWeight: 800, color: '#0f172a', marginTop: 5, letterSpacing: -0.2 }}>
                      AEGIS INTELLIGENCE
                    </div>
                    <div style={{ fontSize: 8.5, color: '#64748b', marginTop: 2 }}>Investigating transaction...</div>
                    <div style={{ fontSize: 8, color: '#0284c7', fontWeight: 700, marginTop: 4 }}>
                      Powered by Gemini AI
                    </div>
                  </div>
                </div>
              </div>

              {/* Card 2: Payment Summary matching Screenshot */}
              <div className="aegis-card" style={{ display: 'flex', flexDirection: 'column' }}>
                <div className="aegis-card-title">
                  <span>Payment Summary</span>
                  <div
                    style={{
                      fontSize: 11,
                      border: '1px solid #e2e8f0',
                      borderRadius: 8,
                      padding: '3px 8px',
                      background: '#f8fafc',
                      color: '#475569',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      cursor: 'pointer',
                    }}
                  >
                    <span>Today</span>
                    <span style={{ fontSize: 9 }}>▾</span>
                  </div>
                </div>

                <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 7, flex: 1, justifyContent: 'space-between' }}>
                  {/* Row 1: Payments Today */}
                  <div className="summary-metric-card">
                    <div className="summary-metric-left">
                      <div className="summary-metric-icon" style={{ background: '#f0fdfa', borderColor: '#ccfbf1', color: '#0d9488' }}>
                        <CreditCard size={18} />
                      </div>
                      <div>
                        <div style={{ fontSize: 10.5, color: '#64748b' }}>Payments Today</div>
                        <div className="summary-metric-val">128</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div className="summary-trend up">
                        <TrendingUp size={12} /> 12%
                      </div>
                      <div className="mini-sparkline">
                        {[8, 14, 11, 18, 22].map((h, i) => (
                          <div key={i} className="mini-sparkline-bar" style={{ height: `${h}px`, background: '#0d9488', opacity: 0.25 + i * 0.18 }} />
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Row 2: Active Verifications */}
                  <div className="summary-metric-card">
                    <div className="summary-metric-left">
                      <div className="summary-metric-icon" style={{ background: '#eff6ff', borderColor: '#dbeafe', color: '#2563eb' }}>
                        <Clock size={18} />
                      </div>
                      <div>
                        <div style={{ fontSize: 10.5, color: '#64748b' }}>Active Verifications</div>
                        <div className="summary-metric-val">07</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div className="summary-trend up">
                        <TrendingUp size={12} /> 2%
                      </div>
                      <div className="mini-sparkline">
                        {[6, 11, 9, 15, 20].map((h, i) => (
                          <div key={i} className="mini-sparkline-bar" style={{ height: `${h}px`, background: '#2563eb', opacity: 0.25 + i * 0.18 }} />
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Row 3: Completed Payments */}
                  <div className="summary-metric-card">
                    <div className="summary-metric-left">
                      <div className="summary-metric-icon" style={{ background: '#f0fdf4', borderColor: '#dcfce7', color: '#16a34a' }}>
                        <CheckCircle2 size={18} />
                      </div>
                      <div>
                        <div style={{ fontSize: 10.5, color: '#64748b' }}>Completed Payments</div>
                        <div className="summary-metric-val">94</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div className="summary-trend up">
                        <TrendingUp size={12} /> 18%
                      </div>
                      <div className="mini-sparkline">
                        {[8, 12, 16, 19, 23].map((h, i) => (
                          <div key={i} className="mini-sparkline-bar" style={{ height: `${h}px`, background: '#16a34a', opacity: 0.25 + i * 0.18 }} />
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Row 4: Cancelled Payments */}
                  <div className="summary-metric-card">
                    <div className="summary-metric-left">
                      <div className="summary-metric-icon" style={{ background: '#fef2f2', borderColor: '#fee2e2', color: '#dc2626' }}>
                        <AlertOctagon size={18} />
                      </div>
                      <div>
                        <div style={{ fontSize: 10.5, color: '#64748b' }}>Cancelled Payments</div>
                        <div className="summary-metric-val">11</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div className="summary-trend down">
                        <TrendingDown size={12} /> 5%
                      </div>
                      <div className="mini-sparkline">
                        {[22, 18, 14, 10, 6].map((h, i) => (
                          <div key={i} className="mini-sparkline-bar" style={{ height: `${h}px`, background: '#dc2626', opacity: 0.9 - i * 0.15 }} />
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Row 5: Verification Incomplete */}
                  <div className="summary-metric-card">
                    <div className="summary-metric-left">
                      <div className="summary-metric-icon" style={{ background: '#fffbeb', borderColor: '#fef3c7', color: '#d97706' }}>
                        <AlertTriangle size={18} />
                      </div>
                      <div>
                        <div style={{ fontSize: 10.5, color: '#64748b' }}>Verification Incomplete</div>
                        <div className="summary-metric-val">16</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div className="summary-trend down" style={{ color: '#dc2626' }}>
                        <TrendingDown size={12} /> 3%
                      </div>
                      <div className="mini-sparkline">
                        {[19, 15, 12, 9, 7].map((h, i) => (
                          <div key={i} className="mini-sparkline-bar" style={{ height: `${h}px`, background: '#d97706', opacity: 0.85 - i * 0.14 }} />
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Card 3: Live Payment Investigation (Wide Bottom Card) */}
            <div className="aegis-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#0f172a' }}>
                    Live Payment Investigation
                  </h3>
                  <span style={{ background: '#fef3c7', color: '#b45309', padding: '3px 9px', borderRadius: 6, fontSize: 10.5, fontWeight: 700 }}>
                    In Progress
                  </span>
                </div>
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    background: '#ecfdf5',
                    color: '#065f46',
                    border: '1px solid #d1fae5',
                    padding: '3px 10px',
                    borderRadius: 20,
                    fontSize: 11,
                    fontWeight: 700,
                  }}
                >
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981' }} />
                  Live
                </div>
              </div>

              <div className="investigation-grid-split">
                {/* Left Side: Stages Timeline Stepper matching Screenshot */}
                <div className="stage-timeline-list">
                  <div className="stage-timeline-item">
                    <span className="stage-timeline-bullet completed">
                      <CheckCircle2 size={16} />
                    </span>
                    <div className="stage-timeline-name">
                      <span>Payment Initiated</span>
                      <span className="stage-timeline-time">10:24:12 AM</span>
                    </div>
                    <div className="stage-timeline-detail">Transaction details received</div>
                  </div>

                  <div className="stage-timeline-item">
                    <span className="stage-timeline-bullet completed">
                      <CheckCircle2 size={16} />
                    </span>
                    <div className="stage-timeline-name">
                      <span>Risk Assessment</span>
                      <span className="stage-timeline-time">10:24:13 AM</span>
                    </div>
                    <div className="stage-timeline-detail">Analyzing transaction and user behavior</div>
                  </div>

                  <div className="stage-timeline-item">
                    <span className="stage-timeline-bullet active" style={{ color: '#8b5cf6' }}>
                      <Cpu size={16} />
                    </span>
                    <div className="stage-timeline-name">
                      <span>AI Investigation</span>
                      <span className="stage-timeline-time">10:24:15 AM</span>
                    </div>
                    <div className="stage-timeline-detail">Analyzing conversation evidence...</div>
                  </div>

                  <div className="stage-timeline-item">
                    <span className="stage-timeline-bullet pending">
                      <Clock size={16} />
                    </span>
                    <div className="stage-timeline-name">
                      <span>Customer Verification</span>
                      <span className="stage-timeline-time">Pending</span>
                    </div>
                    <div className="stage-timeline-detail">Waiting for user response</div>
                  </div>

                  <div className="stage-timeline-item">
                    <span className="stage-timeline-bullet pending">
                      <Clock size={16} />
                    </span>
                    <div className="stage-timeline-name">
                      <span>Policy Decision</span>
                      <span className="stage-timeline-time">Pending</span>
                    </div>
                    <div className="stage-timeline-detail">Evaluating risk and applying rules.</div>
                  </div>

                  <div className="stage-timeline-item">
                    <span className="stage-timeline-bullet pending">
                      <Clock size={16} />
                    </span>
                    <div className="stage-timeline-name">
                      <span>Customer Intervention</span>
                      <span className="stage-timeline-time">Pending</span>
                    </div>
                    <div className="stage-timeline-detail">Sending notification to user</div>
                  </div>
                </div>

                {/* Right Side: Tabbed Box */}
                <div className="investigation-tabs-box">
                  <div className="investigation-tabs-bar">
                    <button
                      type="button"
                      className={`investigation-tab-btn ${investigationTab === 'Transcript' ? 'active' : ''}`}
                      onClick={() => setInvestigationTab('Transcript')}
                    >
                      Transcript
                    </button>
                    <button
                      type="button"
                      className={`investigation-tab-btn ${investigationTab === 'Conversation' ? 'active' : ''}`}
                      onClick={() => setInvestigationTab('Conversation')}
                    >
                      Conversation
                    </button>
                    <button
                      type="button"
                      className={`investigation-tab-btn ${investigationTab === 'AI Analysis' ? 'active' : ''}`}
                      onClick={() => setInvestigationTab('AI Analysis')}
                    >
                      AI Analysis
                    </button>
                  </div>

                  <div className="investigation-tab-body">
                    {investigationTab === 'Transcript' ? (
                      <>
                        {/* Audio Waveform Player Bar matching Screenshot */}
                        <div className="audio-player-bar">
                          <button
                            type="button"
                            className="audio-play-btn"
                            onClick={() => setIsPlayingAudio(!isPlayingAudio)}
                            title={isPlayingAudio ? 'Pause Audio' : 'Play Audio Capture'}
                          >
                            {isPlayingAudio ? <Pause size={14} /> : <Play size={14} style={{ marginLeft: 2 }} />}
                          </button>
                          <div className="waveform-canvas-mock">
                            {Array.from({ length: 42 }).map((_, i) => {
                              const barHeight = Math.sin(i * 0.45) * 8 + 12;
                              const isActive = (audioProgress / 28) * 42 >= i;
                              return (
                                <div
                                  key={i}
                                  className={`waveform-bar ${isActive ? 'active' : ''}`}
                                  style={{ height: `${barHeight}px` }}
                                />
                              );
                            })}
                          </div>
                          <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#64748b' }}>
                            0:{audioProgress < 10 ? `0${audioProgress}` : audioProgress} / 0:28
                          </span>
                          <button
                            type="button"
                            style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#64748b' }}
                            title="Download Audio Capture"
                          >
                            <Download size={15} />
                          </button>
                        </div>

                        {/* Transcript Dialogue List matching Screenshot */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 180, overflowY: 'auto' }}>
                          {selectedUser.transcriptEntries.map((turn, idx) => (
                            <div
                              key={idx}
                              className={`transcript-card-row ${turn.role === 'caller' ? 'adversary' : 'user'}`}
                            >
                              <div className={`transcript-icon-box ${turn.role === 'caller' ? 'caller' : 'customer'}`}>
                                {turn.role === 'caller' ? <PhoneIncoming size={13} /> : <User size={13} />}
                              </div>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
                                  <span style={{ fontSize: 11, fontWeight: 700, color: turn.role === 'caller' ? '#b91c1c' : '#0f766e' }}>
                                    {turn.speaker}{' '}
                                    <span style={{ fontSize: 9.5, color: '#94a3b8', fontWeight: 400 }}>{turn.time}</span>
                                  </span>
                                  {turn.threatBadge && (
                                    <span className={`threat-tag ${turn.threatTone === 'danger' ? 'danger' : 'warning'}`}>
                                      {turn.threatBadge}
                                    </span>
                                  )}
                                </div>
                                <div style={{ fontSize: 11, color: '#334155', lineHeight: 1.45 }}>{turn.text}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : investigationTab === 'Conversation' ? (
                      /* Conversation Tab: Mirrors the phone call with Gemini */
                      <div style={{ display: 'flex', flexDirection: 'column', height: 240 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, paddingBottom: 6, borderBottom: '1px solid #e2e8f0' }}>
                          <span style={{ fontSize: 11, fontWeight: 700, color: '#0f172a' }}>
                            Live Audio Channel: User Mobile Phone
                          </span>
                          <span style={{ background: '#e0f2fe', color: '#0369a1', padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700 }}>
                            Gemini 3.8 Live Voice
                          </span>
                        </div>
                        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 7, padding: '2px 0' }}>
                          {conversationMessages.map((m, idx) => (
                            <div
                              key={idx}
                              style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: m.role === 'customer' ? 'flex-end' : 'flex-start',
                              }}
                            >
                              <div
                                style={{
                                  maxWidth: '85%',
                                  padding: '7px 11px',
                                  borderRadius: 9,
                                  background: m.role === 'customer' ? '#e0f2fe' : '#f1f5f9',
                                  color: m.role === 'customer' ? '#0369a1' : '#1e293b',
                                  fontSize: 11,
                                  lineHeight: 1.45,
                                }}
                              >
                                {m.text}
                              </div>
                              <span style={{ fontSize: 9, color: '#94a3b8', marginTop: 2 }}>
                                {m.role === 'customer' ? 'Customer' : 'Aegis Security'} · {m.time}
                              </span>
                            </div>
                          ))}
                        </div>
                        <div style={{ marginTop: 8, padding: '6px 10px', background: '#f8fafc', borderRadius: 8, fontSize: 10.5, color: '#64748b' }}>
                          💡 Speak or reply directly inside the <strong>Mobile Layout Preview</strong> on the right to interact with Gemini.
                        </div>
                      </div>
                    ) : (
                      /* AI Analysis Tab */
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 11.5 }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                          <div style={{ padding: 10, background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                            <div style={{ fontSize: 10, color: '#64748b' }}>Risk Sentiment</div>
                            <div style={{ fontWeight: 800, color: '#b91c1c', fontSize: 13, marginTop: 2 }}>
                              {selectedUser.riskScore >= 80 ? 'CONFIRMED COERCION' : 'ELEVATED SUSPICION'}
                            </div>
                          </div>
                          <div style={{ padding: 10, background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                            <div style={{ fontSize: 10, color: '#64748b' }}>Decision Recommendation</div>
                            <div style={{ fontWeight: 800, color: '#0369a1', fontSize: 13, marginTop: 2 }}>
                              {selectedUser.riskScore >= 80 ? 'PROTECTIVE HOLD' : 'VERIFICATION REQUIRED'}
                            </div>
                          </div>
                        </div>

                        <div style={{ padding: 10, background: '#fff5f5', borderRadius: 8, border: '1px solid #fee2e2' }}>
                          <div style={{ fontWeight: 700, color: '#b91c1c', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                            <AlertTriangle size={14} /> Critical Evidence Signals Identified:
                          </div>
                          <ul style={{ margin: 0, paddingLeft: 18, color: '#7f1d1d', lineHeight: 1.5, fontSize: 10.5 }}>
                            <li>Fake Law Enforcement / CBI Authority Impersonation</li>
                            <li>Coaching to dismiss bank safeguards and demand secrecy</li>
                            <li>Premature Liquidation of deposits prior to transfer execution</li>
                            <li>Device engaged in active call during transfer execution</li>
                          </ul>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ================================================================= */}
          {/* Column 3 (Right): Mobile Layout Preview (Top) + Demo Scenarios (Bottom) */}
          {/* ================================================================= */}
          <div className="right-dashboard-stack">
            {/* Top Right: Mobile Layout Preview matching Reference Screenshot */}
            <div className="aegis-card" style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="aegis-card-title" style={{ marginBottom: 10 }}>
                <span>Mobile Layout Preview</span>
              </div>

              {/* iPhone Frame */}
              <div className="iphone-frame">
                <div className="iphone-notch" />
                <div className="iphone-screen">
                  {/* Statusbar */}
                  <div className="iphone-statusbar">
                    <span>9:41</span>
                    <span style={{ fontSize: 9.5, display: 'flex', gap: 4, alignItems: 'center' }}>
                      <span>5G</span>
                      <span>100%</span>
                    </span>
                  </div>

                  {/* Mode Switcher Tabs inside Phone for easy inspection */}
                  <div className="phone-mode-switcher" style={{ margin: '4px 10px 0' }}>
                    <button
                      type="button"
                      className={`phone-mode-btn ${mobileViewMode === 'send_money' ? 'active' : ''}`}
                      onClick={() => setMobileViewMode('send_money')}
                    >
                      💳 Send Money
                    </button>
                    <button
                      type="button"
                      className={`phone-mode-btn ${mobileViewMode === 'call' ? 'active' : ''}`}
                      onClick={() => {
                        setMobileViewMode('call');
                        if (!mobileCallActive) {
                          setMobileCallActive(true);
                          setMobileCallStatus('CONNECTED');
                        }
                      }}
                    >
                      📞 Security Call (Gemini)
                    </button>
                  </div>

                  {/* Phone Body Area */}
                  {mobileViewMode === 'send_money' ? (
                    /* Standard Send Money Screen matching Screenshot */
                    <div className="iphone-body">
                      {/* Top Bar with Send Money */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingBottom: 10, marginBottom: 10, borderBottom: '1px solid #f1f5f9' }}>
                        <span style={{ fontSize: 16, cursor: 'pointer', color: '#0f172a' }}>←</span>
                        <strong style={{ fontSize: 13, color: '#0f172a' }}>Send Money</strong>
                      </div>

                      {/* Beneficiary Card matching Screenshot */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 10,
                          padding: '10px 12px',
                          background: '#ffffff',
                          borderRadius: 12,
                          border: '1px solid #f1f5f9',
                          marginBottom: 14,
                        }}
                      >
                        <div
                          style={{
                            width: 38,
                            height: 38,
                            borderRadius: '50%',
                            background: '#fef3c7',
                            color: '#78350f',
                            display: 'grid',
                            placeItems: 'center',
                            fontWeight: 700,
                            fontSize: 12.5,
                          }}
                        >
                          RS
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 700, fontSize: 12.5, color: '#0f172a' }}>
                            Rohit Sharma
                          </div>
                          <div style={{ fontSize: 10.5, color: '#64748b' }}>
                            UPI • rohit@upi
                          </div>
                        </div>
                      </div>

                      {/* Large Amount matching Screenshot */}
                      <div style={{ fontSize: 26, fontWeight: 800, color: '#0f172a', margin: '2px 0 14px', letterSpacing: -0.5 }}>
                        ₹ {Number(mobileAmount || 250000).toLocaleString('en-IN')}
                      </div>

                      {/* Payment note input matching Screenshot */}
                      <div style={{ marginBottom: 'auto' }}>
                        <input
                          type="text"
                          value={mobilePurpose}
                          onChange={(e) => setMobilePurpose(e.target.value)}
                          style={{
                            width: '100%',
                            padding: '8px 10px',
                            borderRadius: 8,
                            border: '1px solid #e2e8f0',
                            fontSize: 11,
                            background: '#f8fafc',
                            color: '#334155',
                            outline: 'none',
                          }}
                          placeholder="Payment for official fees"
                        />
                      </div>

                      {/* Protected by AegisPay banner matching Screenshot */}
                      <div
                        style={{
                          marginTop: 18,
                          marginBottom: 12,
                          padding: '10px 12px',
                          background: '#f0fdfa',
                          border: '1px solid #ccfbf1',
                          borderRadius: 10,
                          display: 'flex',
                          gap: 10,
                          alignItems: 'center',
                        }}
                      >
                        <ShieldCheck size={20} color="#0d9488" style={{ flexShrink: 0 }} />
                        <div style={{ fontSize: 10, color: '#134e4a', lineHeight: 1.35 }}>
                          <strong>Protected by AegisPay</strong>
                          <div>Your payment is analyzed for fraud risks in real time.</div>
                        </div>
                      </div>

                      {/* Pay Now Button */}
                      <button
                        type="button"
                        onClick={handleMobilePayNow}
                        disabled={isAnalyzingPay}
                        style={{
                          width: '100%',
                          padding: '11px',
                          borderRadius: 8,
                          border: 'none',
                          background: '#0d9488',
                          color: '#ffffff',
                          fontWeight: 700,
                          fontSize: 12.5,
                          cursor: 'pointer',
                          boxShadow: '0 2px 8px rgba(13, 148, 136, 0.25)',
                          transition: 'all 0.15s',
                        }}
                      >
                        {isAnalyzingPay ? 'Analyzing with Aegis AI...' : 'Pay Now'}
                      </button>
                    </div>
                  ) : (
                    /* In-Call Phone Screen: Live Call with Gemini AI matching User Requirement */
                    <div className="iphone-body" style={{ padding: '10px 12px' }}>
                      {mobileCallStatus === 'RINGING' ? (
                        /* Ringing State */
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', textAlign: 'center' }}>
                          <div
                            style={{
                              width: 60,
                              height: 60,
                              borderRadius: '50%',
                              background: '#0d9488',
                              color: '#ffffff',
                              display: 'grid',
                              placeItems: 'center',
                              boxShadow: '0 0 0 10px rgba(13, 148, 136, 0.2)',
                              marginBottom: 12,
                            }}
                          >
                            <PhoneIncoming size={28} />
                          </div>
                          <h4 style={{ margin: 0, fontSize: 15, color: '#0f172a' }}>AegisPay Security</h4>
                          <p style={{ margin: '3px 0 16px', fontSize: 10.5, color: '#64748b' }}>
                            Fraud Protection Outbound Call
                          </p>
                          <div style={{ fontSize: 10, color: '#0284c7', background: '#e0f2fe', padding: '3px 8px', borderRadius: 6, marginBottom: 20 }}>
                            Powered by Gemini 3.8 Live Voice
                          </div>

                          <div style={{ display: 'flex', gap: 20 }}>
                            <button
                              type="button"
                              onClick={handleDeclineCall}
                              style={{
                                width: 48,
                                height: 48,
                                borderRadius: '50%',
                                background: '#ef4444',
                                color: '#fff',
                                border: 'none',
                                display: 'grid',
                                placeItems: 'center',
                                cursor: 'pointer',
                              }}
                              title="Decline Call"
                            >
                              <PhoneOff size={20} />
                            </button>
                            <button
                              type="button"
                              onClick={handleAcceptCall}
                              style={{
                                width: 48,
                                height: 48,
                                borderRadius: '50%',
                                background: '#10b981',
                                color: '#fff',
                                border: 'none',
                                display: 'grid',
                                placeItems: 'center',
                                cursor: 'pointer',
                                boxShadow: '0 4px 12px rgba(16, 185, 129, 0.4)',
                              }}
                              title="Accept Call"
                            >
                              <PhoneCall size={20} />
                            </button>
                          </div>
                        </div>
                      ) : (
                        /* Connected Call State: Interactive Gemini Conversation right on the phone! */
                        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                          {/* Call Header */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 6, borderBottom: '1px solid #f1f5f9', marginBottom: 6 }}>
                            <div>
                              <div style={{ fontSize: 11, fontWeight: 700, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 5 }}>
                                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981' }} />
                                AegisPay Security Officer
                              </div>
                              <div style={{ fontSize: 9.5, color: '#64748b' }}>
                                Call Active · 00:{callDuration < 10 ? `0${callDuration}` : callDuration}
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={handleEndCall}
                              style={{
                                width: 28,
                                height: 28,
                                borderRadius: '50%',
                                background: '#fee2e2',
                                color: '#ef4444',
                                border: 'none',
                                display: 'grid',
                                placeItems: 'center',
                                cursor: 'pointer',
                              }}
                              title="End Call"
                            >
                              <PhoneOff size={13} />
                            </button>
                          </div>

                          {/* Sound wave visualizer */}
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 2, height: 16, margin: '2px 0 6px' }}>
                            {Array.from({ length: 18 }).map((_, i) => (
                              <div
                                key={i}
                                style={{
                                  width: 2,
                                  height: `${Math.sin(i * 0.7 + callDuration) * 6 + 9}px`,
                                  background: '#0d9488',
                                  borderRadius: 1,
                                  transition: 'height 0.2s',
                                }}
                              />
                            ))}
                          </div>

                          {/* Dialogue Turns */}
                          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6, paddingRight: 2 }}>
                            {conversationMessages.map((m, idx) => (
                              <div
                                key={idx}
                                style={{
                                  display: 'flex',
                                  flexDirection: 'column',
                                  alignItems: m.role === 'customer' ? 'flex-end' : 'flex-start',
                                }}
                              >
                                <div
                                  style={{
                                    maxWidth: '88%',
                                    padding: '6px 9px',
                                    borderRadius: 8,
                                    background: m.role === 'customer' ? '#0d9488' : '#f1f5f9',
                                    color: m.role === 'customer' ? '#ffffff' : '#0f172a',
                                    fontSize: 10.5,
                                    lineHeight: 1.4,
                                  }}
                                >
                                  {m.text}
                                </div>
                                <span style={{ fontSize: 8.5, color: '#94a3b8', marginTop: 1 }}>
                                  {m.role === 'customer' ? 'You' : 'Officer (Gemini)'} · {m.time}
                                </span>
                              </div>
                            ))}
                            {isGeminiReplying && (
                              <div style={{ fontSize: 9.5, color: '#0284c7', fontStyle: 'italic', padding: '2px 6px' }}>
                                Officer is speaking...
                              </div>
                            )}
                          </div>

                          {/* Quick reply chips */}
                          <div style={{ display: 'flex', gap: 4, margin: '6px 0 4px', overflowX: 'auto', whiteSpace: 'nowrap' }}>
                            {["I'm scared. What should I do?", 'They said they are police', 'They told me not to hang up'].map((chip, idx) => (
                              <button
                                key={idx}
                                type="button"
                                onClick={() => handleSendPhoneMessage(chip)}
                                style={{
                                  fontSize: 8.5,
                                  padding: '3px 6px',
                                  borderRadius: 12,
                                  border: '1px solid #cbd5e1',
                                  background: '#f8fafc',
                                  color: '#334155',
                                  cursor: 'pointer',
                                  flexShrink: 0,
                                }}
                              >
                                {chip}
                              </button>
                            ))}
                          </div>

                          {/* Customer Phone Message Input Bar */}
                          <div style={{ display: 'flex', gap: 4, marginTop: 2 }}>
                            <input
                              type="text"
                              value={customerPhoneInput}
                              onChange={(e) => setCustomerPhoneInput(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleSendPhoneMessage(customerPhoneInput);
                              }}
                              placeholder="Speak or reply to officer..."
                              style={{
                                flex: 1,
                                padding: '6px 8px',
                                borderRadius: 6,
                                border: '1px solid #cbd5e1',
                                fontSize: 10,
                                outline: 'none',
                              }}
                            />
                            <button
                              type="button"
                              onClick={() => setIsTranscribeModalOpen(true)}
                              style={{
                                width: 28,
                                height: 28,
                                borderRadius: 6,
                                border: '1px solid #cbd5e1',
                                background: '#f8fafc',
                                color: '#0284c7',
                                display: 'grid',
                                placeItems: 'center',
                                cursor: 'pointer',
                              }}
                              title="Speak via Microphone (gemini-3.5-transcribe)"
                            >
                              <Mic size={13} />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleSendPhoneMessage(customerPhoneInput)}
                              style={{
                                width: 28,
                                height: 28,
                                borderRadius: 6,
                                border: 'none',
                                background: '#0d9488',
                                color: '#fff',
                                display: 'grid',
                                placeItems: 'center',
                                cursor: 'pointer',
                              }}
                              title="Send Message"
                            >
                              <Send size={12} />
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Bottom Right: Demo Scenarios matching Reference Screenshot */}
            <div className="aegis-card" style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="aegis-card-title" style={{ marginBottom: 10 }}>
                <span>Demo Scenarios</span>
              </div>

              <div>
                {scenarioRadioOptions.map((opt) => {
                  const isSelected = selectedScenarioKey === opt.key;
                  return (
                    <div
                      key={opt.key}
                      className={`scenario-radio-item ${isSelected ? 'selected' : ''}`}
                      onClick={() => handleRunScenario(opt.key)}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 11 }}>
                        <span
                          style={{
                            width: 12,
                            height: 12,
                            borderRadius: '50%',
                            border: isSelected ? '4px solid #0d9488' : '1.5px solid #94a3b8',
                            background: '#fff',
                            display: 'inline-block',
                            flexShrink: 0,
                          }}
                        />
                        <span style={{ fontWeight: isSelected ? 700 : 500, color: '#0f172a' }}>{opt.label}</span>
                      </div>
                      <span className={`score-badge-pill ${opt.tone}`}>{opt.risk}</span>
                    </div>
                  );
                })}

                <button
                  type="button"
                  onClick={() => handleRunScenario(selectedScenarioKey)}
                  style={{
                    width: '100%',
                    padding: '11px',
                    borderRadius: 8,
                    border: 'none',
                    background: '#0d5c63',
                    color: '#ffffff',
                    fontWeight: 700,
                    fontSize: 12.5,
                    cursor: 'pointer',
                    marginTop: 8,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                    boxShadow: '0 2px 8px rgba(13, 92, 99, 0.25)',
                  }}
                >
                  <Play size={13} fill="#ffffff" /> Run Scenario
                </button>
              </div>
            </div>
          </div>
        </main>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* Audio Transcribe Modal */}
      {/* --------------------------------------------------------------------- */}
      <AudioTranscribeModal
        isOpen={isTranscribeModalOpen}
        onClose={() => setIsTranscribeModalOpen(false)}
        onTranscriptionComplete={(text) => handleSendPhoneMessage(text)}
      />
    </div>
  );
}
