import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ArrowDownLeft, BookOpen, Check,
  FileSearch, Headphones, Landmark, LockKeyhole, MessageSquareText,
  Mic, MicOff, Phone as PhoneIcon, PhoneCall, PhoneOff, RotateCcw, Search, ShieldAlert, ShieldCheck,
  Smartphone, Volume2, VolumeX, X,
} from 'lucide-react';
import { BackendHealthBadge } from './components/BackendHealthBadge';
import {
  evaluateRiskApi,
  evaluateRiskLocally,
  RiskAssessmentResponse,
  SCENARIO_CATALOG,
  TransactionEvidenceInput,
} from './api/riskApi';

type Scenario =
  | 'digital_arrest'
  | 'investment_scam'
  | 'fake_invoice'
  | 'mule_network'
  | 'legitimate_high_value'
  | 'ambiguous_payment'
  | 'routine'
  | 'impersonation'
  | 'verified'
  | 'unavailable'
  | 'agent';

type Surface = 'Live Payments' | 'Verification Sources' | 'Settings' | 'Agent Payments';
type PayState =
  | 'Awaiting verification'
  | 'Awaiting customer decision'
  | 'Verification incomplete'
  | 'Approved'
  | 'Cancelled'
  | 'Completed without check'
  | 'Completed after warning';
type CallState =
  | 'Not required'
  | 'Scheduled'
  | 'Calling'
  | 'Connected'
  | 'In progress'
  | 'Completed'
  | 'Declined'
  | 'No answer'
  | 'Error'
  | 'Unavailable';
type VerifyResult =
  | 'Confirmed'
  | 'Contradicted'
  | 'No matching record'
  | 'Source unavailable'
  | 'Not independently verifiable';
type Mode = 'voice' | 'chat';
type Statement = { question: string; answer: string; source: 'typed' | 'speech' | 'demo response'; at?: string };
type Audit = { title: string; detail: string; at: string };

type Tx = {
  id: string;
  customer: string;
  customerId: string;
  recipient: string;
  amount: number;
  initiated: string;
  payment: PayState;
  call: CallState;
  known: boolean;
  reference: string;
  purpose: string;
  statements: Statement[];
  audit: Audit[];
  attempt: number;
  result: VerifyResult;
  claim: string;
  claimInstitution?: string;
  claimInstruction?: string;
  claimReference?: string;
  channel?: Mode;
  reason: string;
  process: string;
  concern?: boolean;
  scenario?: Scenario;
  assessment?: RiskAssessmentResponse;
};

const scenarios: Record<
  Scenario,
  { label: string; recipient: string; amount: number; reference: string; purpose: string; known: boolean }
> = {
  digital_arrest: {
    label: '1. Digital Arrest / Coercion',
    recipient: SCENARIO_CATALOG.digital_arrest.recipient,
    amount: SCENARIO_CATALOG.digital_arrest.amount,
    reference: SCENARIO_CATALOG.digital_arrest.reference,
    purpose: SCENARIO_CATALOG.digital_arrest.purpose,
    known: false,
  },
  investment_scam: {
    label: '2. High-Yield Investment Fraud',
    recipient: SCENARIO_CATALOG.investment_scam.recipient,
    amount: SCENARIO_CATALOG.investment_scam.amount,
    reference: SCENARIO_CATALOG.investment_scam.reference,
    purpose: SCENARIO_CATALOG.investment_scam.purpose,
    known: false,
  },
  fake_invoice: {
    label: '3. Fake Invoice / Routing Mismatch',
    recipient: SCENARIO_CATALOG.fake_invoice.recipient,
    amount: SCENARIO_CATALOG.fake_invoice.amount,
    reference: SCENARIO_CATALOG.fake_invoice.reference,
    purpose: SCENARIO_CATALOG.fake_invoice.purpose,
    known: false,
  },
  mule_network: {
    label: '4. Mule Account Dispersal',
    recipient: SCENARIO_CATALOG.mule_network.recipient,
    amount: SCENARIO_CATALOG.mule_network.amount,
    reference: SCENARIO_CATALOG.mule_network.reference,
    purpose: SCENARIO_CATALOG.mule_network.purpose,
    known: false,
  },
  legitimate_high_value: {
    label: '5. Legitimate High-Value Transfer',
    recipient: SCENARIO_CATALOG.legitimate_high_value.recipient,
    amount: SCENARIO_CATALOG.legitimate_high_value.amount,
    reference: SCENARIO_CATALOG.legitimate_high_value.reference,
    purpose: SCENARIO_CATALOG.legitimate_high_value.purpose,
    known: true,
  },
  ambiguous_payment: {
    label: '6. Ambiguous / Missing Telemetry',
    recipient: SCENARIO_CATALOG.ambiguous_payment.recipient,
    amount: SCENARIO_CATALOG.ambiguous_payment.amount,
    reference: SCENARIO_CATALOG.ambiguous_payment.reference,
    purpose: SCENARIO_CATALOG.ambiguous_payment.purpose,
    known: false,
  },
  routine: {
    label: 'Routine rent (legacy)',
    recipient: 'Maple Grove Properties',
    amount: 18000,
    reference: '',
    purpose: 'Monthly rent',
    known: true,
  },
  impersonation: {
    label: 'Bank impersonation (legacy)',
    recipient: 'Secure Reserve Services',
    amount: 85000,
    reference: '',
    purpose: '',
    known: false,
  },
  verified: {
    label: 'Verified bank request (legacy)',
    recipient: 'Aster Bank Settlement',
    amount: 6500,
    reference: 'ASB-48219',
    purpose: 'Aster Bank settlement instruction',
    known: false,
  },
  unavailable: {
    label: 'Source unavailable (legacy)',
    recipient: 'Northstar Holdings',
    amount: 42000,
    reference: '',
    purpose: '',
    known: false,
  },
  agent: {
    label: 'Agent mandate · secondary',
    recipient: 'Orchid Audio',
    amount: 4500,
    reference: '',
    purpose: 'Headphones purchase',
    known: false,
  },
};

const initialQuestions = [
  'What is this payment for?',
  'Who asked you to make this payment?',
  'Did they give you a reference number?',
];

const fmt = (n: number) => `₹${n.toLocaleString('en-IN')}`;
const stamp = () =>
  new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const fullStamp = () =>
  new Date().toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'medium' });
const shortTime = (value: string) => value.split(', ').at(-1) ?? value;
const classes = (...v: Array<string | false | undefined>) => v.filter(Boolean).join(' ');
const makeAudit = (title: string, detail: string): Audit => ({ title, detail, at: stamp() });

const paymentStatus = (tx: Tx) => {
  if (tx.payment === 'Cancelled') return 'Cancelled';
  if (['Approved', 'Completed without check', 'Completed after warning'].includes(tx.payment))
    return 'Completed';
  return 'Pending';
};

const verificationStatus = (tx: Tx) => {
  if (tx.call === 'Not required') return 'Not required';
  if (['Scheduled', 'Calling'].includes(tx.call)) return 'Calling';
  if (
    tx.payment === 'Verification incomplete' ||
    ['Declined', 'No answer', 'Error', 'Unavailable'].includes(tx.call)
  )
    return 'Incomplete';
  if (/extracting claim|checking .*registry/i.test(tx.process)) return 'Checking claim';
  if (tx.call === 'Connected') return 'Voice connected';
  if (tx.call === 'In progress') return tx.channel === 'chat' ? 'Chat active' : 'Voice connected';
  if (tx.call === 'Completed') return 'Complete';
  return 'Incomplete';
};

const decisionStatus = (tx: Tx) => {
  if (tx.payment === 'Awaiting customer decision') return 'Pending customer choice';
  if (tx.payment === 'Approved') return 'Approved';
  if (tx.payment === 'Completed without check') return 'Completed · check not required';
  if (tx.payment === 'Completed after warning') return 'Customer proceeded after warning';
  if (tx.payment === 'Cancelled') return 'Cancelled';
  if (tx.payment === 'Verification incomplete') return 'Verification incomplete';
  return 'Pending verification';
};

const checkReason = (tx: Tx, threshold: number) => {
  if (tx.scenario === 'agent') return 'Agent payment';
  if (tx.known) return 'Routine payment';
  return tx.amount >= threshold ? 'New payee · Unusual amount' : 'New payee';
};

const seed = (): Tx[] => [
  {
    id: 'AST-240618-0837',
    customer: 'Meera Iyer',
    customerId: 'CU-1028',
    recipient: 'Cedar & Stone Foods',
    amount: 2460,
    initiated: '18 Jun 2024, 09:12:08',
    payment: 'Completed without check',
    call: 'Not required',
    known: true,
    reference: '',
    purpose: 'Groceries',
    statements: [],
    audit: [makeAudit('Payment completed', 'Known recipient · routine payment.')],
    attempt: 0,
    result: 'Not independently verifiable',
    claim: '',
    reason: 'Known payee and routine amount; no additional verification required.',
    process: 'Complete',
    assessment: evaluateRiskLocally({
      amount: 2460,
      recipient_name: 'Cedar & Stone Foods',
      is_first_time_recipient: false,
      is_trusted_beneficiary: true,
      coercive_language_detected: false,
    }),
  },
  {
    id: 'AST-240618-0839',
    customer: 'Kabir Shah',
    customerId: 'CU-1091',
    recipient: 'Riverview Medical',
    amount: 12750,
    initiated: '18 Jun 2024, 09:18:42',
    payment: 'Awaiting verification',
    call: 'Calling',
    known: false,
    reference: '',
    purpose: 'Clinic invoice',
    statements: [],
    audit: [makeAudit('Call ringing', 'Customer verification call started.')],
    attempt: 1,
    result: 'Not independently verifiable',
    claim: '',
    reason: 'Customer review is in progress.',
    process: 'Waiting for customer to answer',
    assessment: evaluateRiskLocally({
      amount: 12750,
      recipient_name: 'Riverview Medical',
      is_first_time_recipient: true,
    }),
  },
  {
    id: 'AST-240618-0840',
    customer: 'Sana Kapoor',
    customerId: 'CU-1103',
    recipient: 'Brightline Consulting',
    amount: 32500,
    initiated: '18 Jun 2024, 09:21:05',
    payment: 'Awaiting verification',
    call: 'In progress',
    channel: 'chat',
    known: false,
    reference: '',
    purpose: 'Consulting deposit',
    statements: [{ question: 'What is this payment for?', answer: 'A project deposit.', source: 'typed', at: '09:23:14' }],
    audit: [makeAudit('Customer connected', 'Verification conversation in progress.')],
    attempt: 1,
    result: 'Not independently verifiable',
    claim: '',
    reason: 'Customer review is in progress.',
    process: 'Listening to customer',
    assessment: evaluateRiskLocally({
      amount: 32500,
      recipient_name: 'Brightline Consulting',
      is_first_time_recipient: true,
      active_call_present: true,
    }),
  },
  {
    id: 'AST-240618-0828',
    customer: 'Arjun Nair',
    customerId: 'CU-0982',
    recipient: 'Aster Bank Fees',
    amount: 1250,
    initiated: '18 Jun 2024, 08:44:19',
    payment: 'Approved',
    call: 'Completed',
    known: false,
    reference: 'ASB-48220',
    purpose: 'Account fee',
    statements: [],
    audit: [makeAudit('Payment completed after approval', 'Aster Bank instruction matched and the simulated transfer completed.')],
    attempt: 1,
    result: 'Confirmed',
    claim: 'Account fee instruction · ASB-48220',
    reason: 'All six instruction fields matched the Aster Bank instruction registry. The simulated payment completed.',
    process: 'Complete',
    assessment: evaluateRiskLocally({
      amount: 1250,
      recipient_name: 'Aster Bank Fees',
      is_first_time_recipient: true,
    }),
  },
  {
    id: 'AST-240618-0824',
    customer: 'Leela Menon',
    customerId: 'CU-1006',
    recipient: 'Westgate Services',
    amount: 68000,
    initiated: '18 Jun 2024, 08:31:50',
    payment: 'Cancelled',
    call: 'Completed',
    known: false,
    reference: '',
    purpose: 'Urgent account protection',
    statements: [],
    audit: [makeAudit('Customer cancelled after warning', 'The customer reviewed the warning and chose to cancel. Money was not sent.')],
    attempt: 1,
    result: 'No matching record',
    claim: 'Safe-account transfer claim',
    reason: 'After a safe-account and pressure warning, the customer chose to cancel. A missing record alone is not proof of fraud.',
    process: 'Complete',
    assessment: evaluateRiskLocally({
      amount: 68000,
      recipient_name: 'Westgate Services',
      is_first_time_recipient: true,
      coercive_language_detected: true,
      active_call_present: true,
    }),
  },
  {
    id: 'AST-240618-0819',
    customer: 'Dev Mehta',
    customerId: 'CU-0951',
    recipient: 'Northstar Holdings',
    amount: 42000,
    initiated: '18 Jun 2024, 08:12:06',
    payment: 'Verification incomplete',
    call: 'Unavailable',
    known: false,
    reference: '',
    purpose: 'Investment instruction',
    statements: [],
    audit: [makeAudit('Verification incomplete', 'Configured source unavailable; funds remain unsent.')],
    attempt: 1,
    result: 'Source unavailable',
    claim: 'Investment instruction',
    reason: 'Required instruction source is unavailable. No payment was sent.',
    process: 'Source unavailable',
    assessment: evaluateRiskLocally({
      amount: 42000,
      recipient_name: 'Northstar Holdings',
      is_first_time_recipient: true,
    }),
  },
];

interface SpeechResultEvent extends Event {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}
interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onerror: ((event: Event & { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type SpeechWindow = Window & {
  SpeechRecognition?: new () => SpeechRecognitionLike;
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
};

type DrawerTab = 'Live verification' | 'Risk assessment' | 'Evidence & checks' | 'Decision & history';

function App() {
  const [scenario, setScenario] = useState<Scenario>('digital_arrest');
  const [surface, setSurface] = useState<Surface>('Live Payments');
  const [records, setRecords] = useState<Tx[]>(seed);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('Live verification');
  const [query, setQuery] = useState('');
  const [paymentFilter, setPaymentFilter] = useState('All payments');
  const [verificationFilter, setVerificationFilter] = useState('All verifications');
  const [guided, setGuided] = useState(true);
  const [demoResponses, setDemoResponses] = useState(true);
  const [mobileView, setMobileView] = useState<'bank' | 'phone'>('bank');
  const [stage, setStage] = useState<
    | 'home'
    | 'form'
    | 'pending'
    | 'ringing'
    | 'active'
    | 'chat'
    | 'processing'
    | 'warning'
    | 'incomplete'
    | 'outcome'
    | 'settings'
    | 'agent'
  >('form');

  const initialScenario = scenarios.digital_arrest;
  const [recipient, setRecipient] = useState(initialScenario.recipient);
  const [amount, setAmount] = useState(initialScenario.amount);
  const [purpose, setPurpose] = useState(initialScenario.purpose);
  const [reference, setReference] = useState(initialScenario.reference);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('chat');
  const [questionIndex, setQuestionIndex] = useState(0);
  const [draft, setDraft] = useState('');
  const [assistantSpeaking, setAssistantSpeaking] = useState(false);
  const [voiceError, setVoiceError] = useState('');
  const [muted, setMuted] = useState(false);
  const [micMuted, setMicMuted] = useState(false);
  const [draftSource, setDraftSource] = useState<Statement['source']>('typed');
  const [duration, setDuration] = useState(0);
  const policyLimit = 25000;
  const [trusted, setTrusted] = useState(false);
  const [consent, setConsent] = useState(true);
  const [agentResult, setAgentResult] = useState<'idle' | 'approved' | 'rejected'>('idle');
  const [agentMerchant, setAgentMerchant] = useState('Other merchant');
  const [agentCategory, setAgentCategory] = useState('Gift cards');
  const [agentAmount, setAgentAmount] = useState('4500');

  const timers = useRef<number[]>([]);
  const recognition = useRef<SpeechRecognitionLike | null>(null);
  const activeRef = useRef(activeId);
  activeRef.current = activeId;
  const stageRef = useRef(stage);
  stageRef.current = stage;
  const selected = records.find((r) => r.id === selectedId) ?? null;
  const activeTx = records.find((r) => r.id === activeId) ?? null;

  const speechConstructor = useMemo(() => {
    if (typeof window === 'undefined') return undefined;
    const w = window as SpeechWindow;
    return w.SpeechRecognition ?? w.webkitSpeechRecognition;
  }, []);
  const voiceSupported = Boolean(speechConstructor);

  const questions = useMemo(() => {
    const list = [...initialQuestions];
    const statements = activeTx?.statements ?? [];
    if (
      statements.some((s) =>
        /urgent|secret|safe account|pressure|quickly|don't tell|not tell/i.test(s.answer)
      )
    ) {
      list.push('Did they ask you to act urgently or keep this payment secret?');
    }
    return list;
  }, [activeTx?.statements]);
  const currentQuestion = questions[Math.min(questionIndex, questions.length - 1)];

  const clearRuntime = useCallback(() => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    try {
      recognition.current?.abort();
    } catch {
      /* browser may already have ended */
    }
    recognition.current = null;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    setAssistantSpeaking(false);
  }, []);

  useEffect(() => () => clearRuntime(), [clearRuntime]);
  useEffect(() => {
    if (!['active', 'chat', 'processing'].includes(stage)) return;
    const id = window.setInterval(() => setDuration((v) => v + 1), 1000);
    return () => window.clearInterval(id);
  }, [stage]);

  function patchTx(id: string, update: Partial<Tx>, event?: { title: string; detail: string }) {
    setRecords((old) =>
      old.map((tx) =>
        tx.id === id
          ? {
              ...tx,
              ...update,
              audit: event ? [makeAudit(event.title, event.detail), ...tx.audit] : tx.audit,
            }
          : tx
      )
    );
  }

  function setProcess(id: string, process: string, call?: CallState) {
    patchTx(id, { process, ...(call ? { call } : {}) });
  }

  function reset(next: Scenario = scenario) {
    clearRuntime();
    const d = scenarios[next] || scenarios.digital_arrest;
    setScenario(next);
    setRecords(seed());
    setSelectedId(null);
    setHighlightId(null);
    setActiveId(null);
    setStage('form');
    setRecipient(d.recipient);
    setAmount(d.amount);
    setPurpose(d.purpose);
    setReference(d.reference);
    setQuestionIndex(0);
    setDraft('');
    setDraftSource('typed');
    setMode('chat');
    setVoiceError('');
    setDuration(0);
    setMuted(false);
    setMicMuted(false);
    setMobileView('bank');
    setSurface(next === 'agent' ? 'Agent Payments' : 'Live Payments');
    setAgentResult('idle');
  }

  function schedule(fn: () => void, delay: number) {
    const id = window.setTimeout(fn, delay);
    timers.current.push(id);
  }

  function buildEvidenceForScenario(selectedScenario: Scenario, txAmount: number, txRecipient: string, txPurpose: string): TransactionEvidenceInput {
    const catalogEntry = SCENARIO_CATALOG[selectedScenario];
    if (catalogEntry) {
      return {
        ...catalogEntry.evidence,
        amount: txAmount,
        recipient_name: txRecipient,
        purpose: txPurpose || catalogEntry.purpose,
      };
    }

    if (selectedScenario === 'routine') {
      return {
        amount: txAmount,
        recipient_name: txRecipient,
        is_first_time_recipient: false,
        is_trusted_beneficiary: true,
        coercive_language_detected: false,
      };
    }

    return {
      amount: txAmount,
      recipient_name: txRecipient,
      recipient_identifier: reference.trim() || 'user@upi',
      purpose: txPurpose,
      customer_id: 'CU-1042',
      is_first_time_recipient: true,
    };
  }

  function sendPayment() {
    if (!recipient.trim() || amount <= 0) return;

    const evidenceInput = buildEvidenceForScenario(scenario, amount, recipient.trim(), purpose.trim());
    const initialAssessment = evaluateRiskLocally(evidenceInput);

    if (
      (scenario === 'routine' || scenario === 'legitimate_high_value') &&
      recipient.trim() === 'Maple Grove Properties'
    ) {
      const tx: Tx = {
        id: 'AST-240618-0843',
        customer: 'Anika Rao',
        customerId: 'CU-1042',
        recipient: recipient.trim(),
        amount,
        initiated: fullStamp(),
        payment: 'Completed without check',
        call: 'Not required',
        known: true,
        reference,
        purpose: purpose || 'Monthly rent',
        statements: [],
        audit: [makeAudit('Payment completed', 'Routine known-recipient payment; verification not required.')],
        attempt: 0,
        result: 'Not independently verifiable',
        claim: '',
        reason: 'Known payee and routine payment; no additional verification required.',
        process: 'Complete',
        scenario,
        assessment: initialAssessment,
      };
      setRecords((old) => [tx, ...old]);
      setActiveId(tx.id);
      setHighlightId(tx.id);
      setStage('outcome');
      schedule(() => setHighlightId((id) => (id === tx.id ? null : id)), 8000);

      // Async backend assessment sync
      evaluateRiskApi(evidenceInput).then((res) => {
        patchTx(tx.id, { assessment: res });
      });
      return;
    }

    if (activeId) {
      const existing = records.find((r) => r.id === activeId);
      if (existing && ['Awaiting verification', 'Verification incomplete'].includes(existing.payment)) {
        retry();
        return;
      }
    }

    const id = `AST-${new Date().toISOString().slice(2, 10).replaceAll('-', '')}-${String(Math.floor(1000 + Math.random() * 8999))}`;
    const tx: Tx = {
      id,
      customer: 'Anika Rao',
      customerId: 'CU-1042',
      recipient: recipient.trim(),
      amount,
      initiated: fullStamp(),
      payment: 'Awaiting verification',
      call: 'Scheduled',
      known: false,
      reference: reference.trim(),
      purpose: purpose.trim(),
      statements: [],
      audit: [makeAudit('Payment submitted', 'Payment created and held pending verification. Money has not been sent.')],
      attempt: 1,
      result: 'Not independently verifiable',
      claim: '',
      reason: 'Awaiting customer verification. Money has not been sent.',
      process: 'Payment awaiting verification',
      concern: false,
      scenario,
      assessment: initialAssessment,
    };

    setRecords((old) => [tx, ...old]);
    setActiveId(id);
    setHighlightId(id);
    setStage('pending');
    setMode('chat');
    setQuestionIndex(0);
    setDraft('');
    schedule(() => setHighlightId((current) => (current === id ? null : current)), 8000);
    if (guided) setSelectedId(id);

    // Call backend API for real assessment and state synchronization
    evaluateRiskApi(evidenceInput).then((res) => {
      patchTx(id, { assessment: res });
    });

    schedule(() => {
      patchTx(id, {
        call: 'Calling',
        process: 'Waiting for customer to answer',
        audit: [makeAudit('Call ringing', 'Aster Bank Verification call is ringing.')],
      });
      setStage((s) => (activeRef.current === id && s === 'pending' ? 'ringing' : s));
      schedule(() => {
        if (activeRef.current === id && stageRef.current === 'ringing') {
          incomplete('The customer did not answer the simulated call.', 'No answer');
        }
      }, 12000);
    }, 1000);
  }

  function retry(transactionId = activeId) {
    if (!transactionId) return;
    const tx = records.find((r) => r.id === transactionId);
    if (!tx || !['Verification incomplete', 'Awaiting verification'].includes(tx.payment)) return;
    clearRuntime();
    setDuration(0);
    setVoiceError('');
    setQuestionIndex(tx.statements.length);
    setDraft('');
    setDraftSource('typed');
    setMicMuted(false);
    setActiveId(transactionId);
    patchTx(
      transactionId,
      {
        payment: 'Awaiting verification',
        call: 'Calling',
        attempt: tx.attempt + 1,
        process: 'Waiting for customer to answer',
        reason: 'Awaiting customer verification. Money has not been sent.',
      },
      {
        title: 'Verification retried',
        detail: `Attempt ${tx.attempt + 1} · same transaction; no duplicate payment created.`,
      }
    );
    setStage('ringing');
    if (guided) setSelectedId(transactionId);
    schedule(() => {
      if (activeRef.current === transactionId && stageRef.current === 'ringing') {
        incomplete('The customer did not answer the simulated call.', 'No answer');
      }
    }, 12000);
  }

  function incomplete(reasonText: string, call: CallState = 'Declined', preserveError = false) {
    const id = activeRef.current;
    if (!id) return;
    clearRuntime();
    patchTx(
      id,
      {
        payment: 'Verification incomplete',
        call,
        process: 'Verification incomplete',
        reason: `${reasonText} Money was not sent.`,
      },
      { title: 'Verification incomplete', detail: `${reasonText} Payment remains unsent.` }
    );
    setStage('incomplete');
    if (!preserveError) setVoiceError('');
  }

  function cancelPayment() {
    if (!activeId) return;
    clearRuntime();
    patchTx(
      activeId,
      {
        payment: 'Cancelled',
        call: 'Completed',
        process: 'Complete',
        reason: 'Cancelled at customer request before payment was sent.',
      },
      { title: 'Payment cancelled', detail: 'Customer cancelled before sending. No money moved.' }
    );
    setStage('outcome');
  }

  function proceedAfterWarning() {
    if (!activeId) return;
    const tx = records.find((r) => r.id === activeId);
    if (!tx || tx.payment !== 'Awaiting customer decision') return;
    clearRuntime();
    const reasonText =
      'Customer chose to proceed after the safety warning. This is a local simulation; no real money moved.';
    patchTx(
      activeId,
      { payment: 'Completed after warning', call: 'Completed', process: 'Customer override recorded', reason: reasonText },
      {
        title: 'Customer proceeded after warning',
        detail: 'Customer explicitly chose to continue despite the safety warning. No real money moved.',
      }
    );
    setStage('outcome');
  }

  function answer(modeChoice: Mode) {
    if (!activeId) return;
    setMode(modeChoice);
    setStage(modeChoice === 'voice' ? 'active' : 'chat');
    setDuration(0);
    setVoiceError('');
    setMicMuted(false);
    const tx = records.find((r) => r.id === activeId);
    setQuestionIndex(tx?.statements.length ?? 0);
    patchTx(
      activeId,
      {
        payment: 'Awaiting verification',
        call: modeChoice === 'voice' ? 'Connected' : 'In progress',
        channel: modeChoice,
        process: modeChoice === 'voice' ? 'Voice verification' : 'Secure chat',
      },
      {
        title: 'Customer connected',
        detail:
          modeChoice === 'voice'
            ? 'Voice verification started by customer.'
            : 'Customer chose secure chat; no microphone permission requested.',
      }
    );
    if (modeChoice === 'voice') startVoice();
  }

  function startVoice() {
    if (!speechConstructor) {
      const message = 'Speech recognition is not supported in this browser. No audio was captured.';
      setVoiceError(message);
      incomplete(message, 'Error', true);
      return;
    }
    if ('speechSynthesis' in window && !muted) {
      speakQuestion();
      return;
    }
    beginRecognition();
  }

  function beginRecognition() {
    if (!speechConstructor) return;
    try {
      const r = new speechConstructor();
      recognition.current = r;
      r.continuous = false;
      r.interimResults = true;
      r.lang = 'en-IN';
      r.onresult = (event) => {
        let finalText = '';
        for (let i = 0; i < event.results.length; i++) finalText += `${event.results[i][0].transcript} `;
        setDraft(finalText.trim());
        setDraftSource('speech');
      };
      r.onerror = (event) => {
        const err = event.error || 'recognition error';
        const message =
          err === 'not-allowed' || err === 'service-not-allowed'
            ? 'Microphone permission was not granted. Nothing was recorded.'
            : `Voice input stopped (${err}). Nothing was submitted.`;
        setVoiceError(message);
        incomplete(message, 'Error', true);
      };
      r.onend = () => {
        if (recognition.current === r) recognition.current = null;
      };
      r.start();
    } catch {
      const message = 'Voice input could not start in this browser. No audio was captured.';
      setVoiceError(message);
      incomplete(message, 'Error', true);
    }
  }

  function speakQuestion(question = currentQuestion) {
    if (!('speechSynthesis' in window) || muted || !question) {
      beginRecognition();
      return;
    }
    try {
      recognition.current?.abort();
      recognition.current = null;
      setAssistantSpeaking(true);
      setProcess(activeRef.current || '', 'Assistant speaking');
      const utterance = new SpeechSynthesisUtterance(question);
      utterance.onend = () => {
        setAssistantSpeaking(false);
        if (activeRef.current && !micMuted) {
          setProcess(activeRef.current, 'Listening for your answer', 'In progress');
          beginRecognition();
        }
      };
      utterance.onerror = () => setAssistantSpeaking(false);
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    } catch {
      setAssistantSpeaking(false);
    }
  }

  function switchToChat() {
    try {
      recognition.current?.stop();
    } catch {
      /* no active session */
    }
    recognition.current = null;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    setAssistantSpeaking(false);
    setMode('chat');
    setStage('chat');
    setVoiceError('');
    if (activeId) {
      setProcess(activeId, 'Secure chat');
      patchTx(
        activeId,
        { call: 'In progress', channel: 'chat' },
        { title: 'Switched to chat', detail: 'Conversation continued without microphone access.' }
      );
    }
  }

  function switchToVoice() {
    if (!voiceSupported || !activeId) return;
    setMode('voice');
    setStage('active');
    setVoiceError('');
    patchTx(
      activeId,
      { call: 'Connected', channel: 'voice', process: 'Voice verification' },
      { title: 'Switched to voice', detail: 'Customer chose voice; browser may request microphone permission.' }
    );
    startVoice();
  }

  function toggleMic() {
    const next = !micMuted;
    setMicMuted(next);
    if (next) {
      try {
        recognition.current?.stop();
      } catch {
        /* no active listener */
      }
      recognition.current = null;
      if (activeId) setProcess(activeId, 'Microphone muted');
    } else if (mode === 'voice' && stage === 'active') {
      if (activeId) setProcess(activeId, 'Listening for your answer', 'In progress');
      beginRecognition();
    }
  }

  function finishAnswer(value = draft, source: Statement['source'] = 'typed') {
    const answerText = value.trim();
    if (!answerText || !activeId) return;
    try {
      recognition.current?.stop();
    } catch {
      /* stopped */
    }
    recognition.current = null;
    const q = currentQuestion;
    const nextStatements = [
      ...(activeTx?.statements ?? []),
      { question: q, answer: answerText, source, at: stamp() },
    ];
    patchTx(
      activeId,
      { statements: nextStatements, process: 'Processing answer', call: 'In progress' },
      {
        title: 'Customer answer submitted',
        detail: `${source === 'speech' ? 'Browser speech transcription' : source === 'demo response' ? 'Presenter demo response' : 'Customer text'} · ${answerText}`,
      }
    );
    setDraft('');
    setDraftSource('typed');
    setStage('processing');
    schedule(() => {
      const followup =
        nextStatements.some((s) =>
          /urgent|secret|safe account|pressure|quickly|don't tell|not tell/i.test(s.answer)
        ) && nextStatements.length === 3;
      if (nextStatements.length < 3 || followup) {
        setQuestionIndex(nextStatements.length);
        setStage(mode === 'voice' && voiceSupported ? 'active' : 'chat');
        setProcess(
          activeId,
          `Question ${nextStatements.length + 1} of ${followup ? 4 : 3}`,
          mode === 'voice' ? 'In progress' : 'In progress'
        );
        if (mode === 'voice') {
          const upcoming =
            nextStatements.length === 3 && followup
              ? 'Did they ask you to act urgently or keep this payment secret?'
              : questions[Math.min(nextStatements.length, questions.length - 1)];
          schedule(() => speakQuestion(upcoming), 180);
        }
      } else evaluate(activeId, nextStatements);
    }, 750);
  }

  function demoResponse() {
    const tx = activeTx;
    if (!tx) return;
    let text = '';
    if (/what is this payment/i.test(currentQuestion)) {
      text =
        scenario === 'digital_arrest' || scenario === 'impersonation'
          ? 'Law enforcement called claiming my identity is linked to a CBI money laundering case; they instructed me to deposit funds.'
          : scenario === 'investment_scam'
            ? 'Apex Yield promised guaranteed daily profit on a private crypto fund; they urged me to transfer before market close.'
            : scenario === 'fake_invoice'
              ? 'Supplier invoice payment for office equipment with updated payment details.'
              : scenario === 'mule_network'
                ? 'Quick cash return to a friend request.'
                : scenario === 'verified'
                  ? 'Aster Bank asked me to make the settlement transfer.'
                  : 'This is an annual lease renewal payment.';
    } else if (/who asked/i.test(currentQuestion)) {
      text =
        scenario === 'digital_arrest' || scenario === 'impersonation'
          ? 'An official identifying as CBI officer Sharma with urgent arrest warrant.'
          : scenario === 'investment_scam'
            ? 'An investment manager on Telegram who said not to tell the bank branch.'
            : scenario === 'fake_invoice'
              ? 'Invoice email received from regular vendor address.'
              : scenario === 'mule_network'
                ? 'Contacted via messaging app for urgent cash transfer.'
                : scenario === 'verified'
                  ? 'Aster Bank gave me the instruction.'
                  : 'The landlord representative.';
    } else if (/reference/i.test(currentQuestion)) {
      text =
        scenario === 'verified'
          ? 'The reference is ASB-48219.'
          : scenario === 'digital_arrest'
            ? 'Court bond clearance reference CBI-84920.'
            : scenario === 'investment_scam'
              ? 'VIP Investment Code INV-39210.'
              : 'They did not give me a reference number.';
    } else {
      text = 'They insisted it was urgent and ordered me not to discuss it with bank staff.';
    }
    setDraft(text);
    setDraftSource('demo response');
  }

  function evaluate(id: string, statements: Statement[]) {
    const tx = records.find((r) => r.id === id);
    if (!tx) return;
    setStage('processing');
    patchTx(
      id,
      { process: 'Extracting claim' },
      { title: 'Claim extraction started', detail: 'Customer statement separated from system interpretation.' }
    );
    schedule(() => {
      const statement = statements.map((s) => s.answer).join(' ');
      const claimsBank = /aster bank|bank (asked|instructed|told|gave)|bank instruction/i.test(statement);
      const institutionMatch = /aster bank/i.test(statement);
      const concern = /safe account|urgent|urgency|secret|pressure|quickly|don't tell|not tell|cbi|arrest|bond/i.test(statement);
      const instructionMatch = /settlement|transfer/i.test(`${tx.purpose} ${statement}`);
      const providedReference = statement.match(/ASB-\d{5}/i)?.[0]?.toUpperCase() || tx.reference;
      const claim = claimsBank
        ? `Aster Bank instruction · ${tx.purpose || statements[0]?.answer} · ${providedReference || 'no reference supplied'}`
        : /safe account|cbi|arrest/i.test(statement)
          ? 'Official protection / authority transfer claim'
          : 'Customer-stated payment purpose';
      const recordMatch =
        providedReference === 'ASB-48219' &&
        tx.customerId === 'CU-1042' &&
        institutionMatch &&
        claimsBank &&
        instructionMatch &&
        tx.recipient === 'Aster Bank Settlement' &&
        tx.amount === 6500;
      const candidate = providedReference === 'ASB-48219';
      const result: VerifyResult =
        scenario === 'unavailable'
          ? 'Source unavailable'
          : recordMatch
            ? 'Confirmed'
            : candidate
              ? 'Contradicted'
              : claimsBank
                ? 'No matching record'
                : 'Not independently verifiable';
      const combinedConcern = concern || ((scenario === 'digital_arrest' || scenario === 'impersonation') && concern);

      patchTx(
        id,
        {
          claim,
          claimInstitution: institutionMatch ? 'Aster Bank' : 'Not stated',
          claimInstruction: tx.purpose || statements[0]?.answer || 'Not stated',
          claimReference: providedReference || 'Not supplied',
          result,
          concern: combinedConcern,
          process: 'Checking local demo registry',
          reason: 'Independent check pending',
        },
        { title: 'Claim extracted', detail: `${claim}. Interpretation is recorded separately.` }
      );

      schedule(() => {
        let payment: PayState = 'Verification incomplete';
        let call: CallState = 'Completed';
        let reasonText = '';
        if (result === 'Source unavailable') {
          payment = 'Verification incomplete';
          call = 'Unavailable';
          reasonText =
            'The configured Aster Bank demo source is unavailable. Verification is incomplete; money was not sent.';
        } else if (result === 'Confirmed' && !combinedConcern) {
          payment = 'Approved';
          reasonText =
            'The reference, customer, institution, instruction, recipient and amount all match the local Aster Bank demo registry. No concern indicators were reported.';
        } else if (
          result === 'No matching record' &&
          /safe account|cbi|arrest|invest/i.test(statement) &&
          /urgent|secret|pressure|quickly|don't tell|not tell/i.test(statement)
        ) {
          payment = 'Awaiting customer decision';
          reasonText =
            'Authority duress or guaranteed scheme markers combined with urgency/secrecy triggered a safety warning. The payment remains unsent until the customer chooses to cancel or continue. A missing record alone is not proof of fraud.';
        } else if (result === 'Contradicted' && combinedConcern) {
          payment = 'Awaiting customer decision';
          reasonText =
            'The referenced instruction did not match registry records, and coercive pressure was reported. The payment remains unsent until the customer chooses to cancel or continue.';
        } else {
          reasonText = `Verification incomplete (${result}). Available evidence is not sufficient for an automatic approval or cancellation. Money was not sent.`;
        }
        const needsChoice = payment === 'Awaiting customer decision';
        patchTx(
          id,
          { payment, call, process: needsChoice ? 'Customer decision required' : 'Decision recorded', reason: reasonText },
          {
            title:
              payment === 'Approved'
                ? 'Payment approved'
                : needsChoice
                  ? 'Safety warning shown'
                  : 'Verification incomplete',
            detail: reasonText,
          }
        );
        setStage(payment === 'Verification incomplete' ? 'incomplete' : needsChoice ? 'warning' : 'outcome');
      }, 850);
    }, 600);
  }

  const filtered = useMemo(
    () =>
      records.filter((tx) => {
        const hay = `${tx.id} ${tx.customer} ${tx.recipient} ${tx.customerId}`.toLowerCase();
        const matchedPayment =
          paymentFilter === 'All payments' ||
          (paymentFilter === 'Needs decision'
            ? tx.payment === 'Awaiting customer decision'
            : paymentStatus(tx) === paymentFilter);
        const status = verificationStatus(tx);
        const matchedVerification =
          verificationFilter === 'All verifications' ||
          (verificationFilter === 'Active'
            ? ['Calling', 'Voice connected', 'Chat active', 'Checking claim'].includes(status)
            : status === verificationFilter);
        return hay.includes(query.toLowerCase()) && matchedPayment && matchedVerification;
      }),
    [records, query, paymentFilter, verificationFilter]
  );

  const counts = useMemo(
    () => ({
      today: records.length,
      active: records.filter((t) =>
        ['Calling', 'Voice connected', 'Chat active', 'Checking claim'].includes(verificationStatus(t))
      ).length,
      completed: records.filter((t) => paymentStatus(t) === 'Completed').length,
      cancelled: records.filter((t) => t.payment === 'Cancelled').length,
      needsDecision: records.filter((t) => t.payment === 'Awaiting customer decision').length,
      incomplete: records.filter((t) => verificationStatus(t) === 'Incomplete').length,
    }),
    [records]
  );

  const nav: { name: Surface; icon: typeof Activity }[] = [
    { name: 'Live Payments', icon: Activity },
    { name: 'Verification Sources', icon: FileSearch },
  ];

  const summaryCards = [
    {
      label: 'Payments today',
      count: counts.today,
      detail: 'All payments',
      onClick: () => {
        setPaymentFilter('All payments');
        setVerificationFilter('All verifications');
      },
      active: paymentFilter === 'All payments' && verificationFilter === 'All verifications',
    },
    {
      label: 'Active verifications',
      count: counts.active,
      detail: 'Voice, chat & checks',
      onClick: () => {
        setPaymentFilter('All payments');
        setVerificationFilter('Active');
      },
      active: verificationFilter === 'Active',
    },
    {
      label: 'Completed payments',
      count: counts.completed,
      detail: 'Simulated transfers',
      onClick: () => {
        setPaymentFilter('Completed');
        setVerificationFilter('All verifications');
      },
      active: paymentFilter === 'Completed',
    },
    {
      label: 'Cancelled payments',
      count: counts.cancelled,
      detail: 'Unsent',
      onClick: () => {
        setPaymentFilter('Cancelled');
        setVerificationFilter('All verifications');
      },
      active: paymentFilter === 'Cancelled',
    },
    {
      label: 'Needs decision',
      count: counts.needsDecision,
      detail: 'Customer choice',
      onClick: () => {
        setPaymentFilter('Needs decision');
        setVerificationFilter('All verifications');
      },
      active: paymentFilter === 'Needs decision',
    },
    {
      label: 'Verification incomplete',
      count: counts.incomplete,
      detail: 'Payment remains pending',
      onClick: () => {
        setPaymentFilter('All payments');
        setVerificationFilter('Incomplete');
      },
      active: verificationFilter === 'Incomplete',
    },
  ];

  const currentPhoneStage = stage;
  const finishDecline = () => incomplete('Customer declined the verification call.', 'Declined');

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">A</span>
          <span>
            Aster <span style={{ fontWeight: 500, color: '#73818d' }}>Bank</span>
          </span>
        </div>
        <div className="topbar-center">
          <span className="online-dot" /> Operations workspace <span>·</span> AegisPay AI Engine
        </div>
        <div className="top-actions">
          <BackendHealthBadge />
          <details className="demo-disclosure" data-testid="simulation-disclosure">
            <summary className="environment">
              <span className="online-dot" style={{ background: '#c2901e', boxShadow: 'none' }} /> DEMO / SIMULATED{' '}
              <span className="disclosure-chevron">⌄</span>
            </summary>
            <div className="demo-disclosure-panel">
              This interactive prototype uses simulated customer records and a deterministic risk engine. All outcomes
              are simulated; there are no real-money transfers, external credit lookups, or production data access.
            </div>
          </details>
          <div className="avatar">AR</div>
        </div>
      </header>
      <div className="layout">
        <aside className="sidebar">
          <div>
            <div className="side-label">OPERATIONS</div>
            <div className="nav-list">
              {nav.map(({ name, icon: Icon }) => (
                <button
                  key={name}
                  data-testid={`nav-${name.toLowerCase().replaceAll(' ', '-')}`}
                  className={classes('nav-item', surface === name && 'active')}
                  onClick={() => setSurface(name)}
                >
                  <Icon />
                  {name}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="side-label">PREFERENCES</div>
            <div className="nav-list">
              <button
                className={classes('nav-item', surface === 'Settings' && 'active')}
                data-testid="nav-settings"
                onClick={() => setSurface('Settings')}
              >
                <BookOpen />
                Settings
              </button>
            </div>
          </div>
          <div className="side-bottom">AEGISPAY AI · SIMULATED FRAUD PREVENTION</div>
        </aside>
        <main className="main">
          <section className="control-bar" id="presenter-controls" data-testid="presenter-controls" aria-label="Demo controls">
            <div className="control-actions">
              <select
                aria-label="Choose demo scenario"
                data-testid="select-scenario"
                className="select"
                value={scenario}
                onChange={(e) => reset(e.target.value as Scenario)}
              >
                <optgroup label="Phase 1 Benchmark Scenarios (Deterministic Risk Engine)">
                  <option value="digital_arrest">1. Digital arrest (authority coercion)</option>
                  <option value="investment_scam">2. High-yield investment fraud</option>
                  <option value="fake_invoice">3. Fake invoice / supplier diversion</option>
                  <option value="mule_network">4. Mule account dispersal</option>
                  <option value="legitimate_high_value">5. Legitimate high-value transfer</option>
                  <option value="ambiguous_payment">6. Ambiguous / incomplete context</option>
                </optgroup>
                <optgroup label="Legacy Prototype Presets">
                  <option value="routine">Routine rent</option>
                  <option value="impersonation">Bank impersonation</option>
                  <option value="verified">Verified bank request</option>
                  <option value="unavailable">Source unavailable</option>
                  <option value="agent">Agent mandate · secondary</option>
                </optgroup>
              </select>
              <button className="button small" data-testid="button-reset" onClick={() => reset()}>
                <RotateCcw />
                Reset
              </button>
              <label className="toggle-line">
                <input
                  type="checkbox"
                  checked={guided}
                  onChange={(e) => setGuided(e.target.checked)}
                  data-testid="toggle-guided-demo"
                />
                Guided mode
              </label>
              <label className="toggle-line">
                <input
                  type="checkbox"
                  checked={demoResponses}
                  onChange={(e) => setDemoResponses(e.target.checked)}
                  data-testid="toggle-demo-responses"
                />
                Example responses
              </label>
            </div>
          </section>
          <div className="mobile-view-select" aria-label="Switch product surface">
            <button
              className={classes('button', mobileView === 'bank' && 'soft')}
              data-testid="button-view-bank"
              onClick={() => setMobileView('bank')}
            >
              <Landmark />
              Bank console
            </button>
            <button
              className={classes('button', mobileView === 'phone' && 'soft')}
              data-testid="button-view-phone"
              onClick={() => setMobileView('phone')}
            >
              <Smartphone />
              Customer phone
            </button>
          </div>
          {surface === 'Live Payments' ? (
            <div className={classes('dashboard-layout', mobileView === 'phone' && 'phone-only')}>
              <div className="bank-console">
                <div className="dashboard-head">
                  <div>
                    <div className="eyebrow">ASTER BANK · PAYMENT SAFETY OPERATIONS</div>
                    <h1>Live payment console</h1>
                    <p className="subhead">
                      Unified operational queue with explainable deterministic risk scoring, policy rules, and auditable
                      lifecycle states.
                    </p>
                  </div>
                </div>
                <div className="summary-strip" data-testid="summary-metrics">
                  {summaryCards.map(({ label, count, detail, onClick, active }) => (
                    <button
                      className={classes('summary-card', active && 'active')}
                      key={label}
                      onClick={onClick}
                      aria-pressed={active}
                      data-testid={`metric-${String(label).toLowerCase().replaceAll(' ', '-')}`}
                    >
                      <span>{label}</span>
                      <strong>{count}</strong>
                      <em>{detail}</em>
                    </button>
                  ))}
                </div>
                {selected && (
                  <TransactionDrawer
                    tx={selected}
                    tab={drawerTab}
                    setTab={setDrawerTab}
                    onClose={() => setSelectedId(null)}
                    onRetry={() => retry(selected.id)}
                    policyLimit={policyLimit}
                  />
                )}
                <section className="card bank-content">
                  <div className="card-pad">
                    <div className="card-head">
                      <div>
                        <div className="card-kicker">BANK-WIDE PAYMENT QUEUE</div>
                        <h2 className="card-title" style={{ marginTop: 5 }}>
                          Payment activity
                        </h2>
                      </div>
                    </div>
                    <div className="queue-tools">
                      <label style={{ position: 'relative', flex: '1 1 220px' }}>
                        <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: '#89969e' }} />
                        <input
                          className="field-input"
                          style={{ paddingLeft: 30 }}
                          placeholder="Search ID, customer or recipient"
                          value={query}
                          onChange={(e) => setQuery(e.target.value)}
                          data-testid="input-queue-search"
                        />
                      </label>
                      <select
                        className="select"
                        aria-label="Filter payment status"
                        value={paymentFilter}
                        onChange={(e) => setPaymentFilter(e.target.value)}
                        data-testid="select-queue-status"
                      >
                        {['All payments', 'Pending', 'Completed', 'Cancelled', 'Needs decision'].map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                      <select
                        className="select"
                        aria-label="Filter verification status"
                        value={verificationFilter}
                        onChange={(e) => setVerificationFilter(e.target.value)}
                        data-testid="select-verification-status"
                      >
                        {[
                          'All verifications',
                          'Active',
                          'Not required',
                          'Calling',
                          'Voice connected',
                          'Chat active',
                          'Checking claim',
                          'Complete',
                          'Incomplete',
                        ].map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                      <span className="mono">{filtered.length} records</span>
                    </div>
                    <div className="queue-wrap">
                      <table className="queue-table">
                        <thead>
                          <tr>
                            <th>Customer / transaction</th>
                            <th>Recipient</th>
                            <th className="amount-head">Amount</th>
                            <th>Initiated</th>
                            <th>Check reason</th>
                            <th>Risk score</th>
                            <th>Verification</th>
                            <th>Payment status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filtered.map((tx) => {
                            const riskTier = tx.assessment?.risk_level ?? 'LOW';
                            const riskTone =
                              riskTier === 'CRITICAL'
                                ? 'red'
                                : riskTier === 'HIGH'
                                  ? 'amber'
                                  : riskTier === 'MEDIUM'
                                    ? 'blue'
                                    : 'green';
                            return (
                              <tr
                                key={tx.id}
                                tabIndex={0}
                                className={classes((tx.id === selectedId || tx.id === highlightId) && 'highlighted')}
                                onClick={() => {
                                  setSelectedId(tx.id);
                                  setDrawerTab('Live verification');
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    setSelectedId(tx.id);
                                    setDrawerTab('Live verification');
                                  }
                                }}
                                data-testid={`row-transaction-${tx.id}`}
                                aria-label={`Open transaction ${tx.id}`}
                              >
                                <td>
                                  <div className="queue-customer">
                                    <strong>{tx.customer}</strong>
                                    <small>{tx.id}</small>
                                  </div>
                                </td>
                                <td>
                                  <div className="queue-recipient">
                                    <span>{tx.recipient}</span>
                                    {!tx.known && <small className="payee-badge">New payee</small>}
                                  </div>
                                </td>
                                <td className="amount-cell">{fmt(tx.amount)}</td>
                                <td>
                                  <time title={tx.initiated}>{shortTime(tx.initiated)}</time>
                                </td>
                                <td>{checkReason(tx, policyLimit)}</td>
                                <td>
                                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    <span className={`pill ${riskTone}`} data-testid={`risk-score-${tx.id}`}>
                                      {tx.assessment
                                        ? `${tx.assessment.risk_score} · ${tx.assessment.risk_level}`
                                        : 'Assessing…'}
                                    </span>
                                    {tx.assessment?.source === 'demo_fallback' && (
                                      <span
                                        className="pill amber"
                                        style={{ fontSize: 9, padding: '1px 5px', opacity: 0.9 }}
                                        title="Offline demo fallback evaluation"
                                        data-testid={`risk-source-${tx.id}`}
                                      >
                                        DEMO
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td>
                                  <span
                                    className={`pill ${
                                      ['Calling', 'Voice connected', 'Chat active', 'Checking claim'].includes(
                                        verificationStatus(tx)
                                      )
                                        ? 'amber'
                                        : verificationStatus(tx) === 'Complete'
                                          ? 'green'
                                          : verificationStatus(tx) === 'Incomplete'
                                            ? 'blue'
                                            : ''
                                    }`}
                                    data-testid={`call-status-${tx.id}`}
                                  >
                                    {verificationStatus(tx)}
                                  </span>
                                </td>
                                <td>
                                  <span
                                    className={`pill ${
                                      paymentStatus(tx) === 'Completed'
                                        ? 'green'
                                        : paymentStatus(tx) === 'Cancelled'
                                          ? 'red'
                                          : tx.payment === 'Awaiting customer decision'
                                            ? 'amber'
                                            : 'blue'
                                    }`}
                                    data-testid={`payment-status-${tx.id}`}
                                  >
                                    {paymentStatus(tx)}
                                  </span>
                                </td>
                              </tr>
                            );
                          })}
                          {!filtered.length && (
                            <tr>
                              <td colSpan={8} style={{ textAlign: 'center', padding: 28, color: '#829099' }}>
                                No payments match these filters.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </section>
                <section className="card" style={{ marginTop: 12 }}>
                  <div className="card-pad" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <ShieldCheck size={17} color="#18745f" />
                    <span className="disclosure">
                      Deterministic engine computes relative risk scores (0–100) using policy rules. Missing signals
                      remain unknown; voice stress is advisory only and never standalone proof of fraud.
                    </span>
                  </div>
                </section>
              </div>
              <div className="phone-wrap">
                <div className="phone-label">
                  <span className="card-kicker">CUSTOMER DEVICE · ANDROID PREVIEW</span>
                  <span className="pill blue">Anika Rao</span>
                </div>
                <CustomerPhone
                  scenario={scenario}
                  stage={currentPhoneStage}
                  recipient={recipient}
                  setRecipient={setRecipient}
                  amount={amount}
                  setAmount={setAmount}
                  purpose={purpose}
                  setPurpose={setPurpose}
                  reference={reference}
                  setReference={setReference}
                  tx={activeTx}
                  mode={mode}
                  question={currentQuestion}
                  questionIndex={questionIndex}
                  questionsCount={questions.length}
                  draft={draft}
                  setDraft={(v) => {
                    setDraft(v);
                    setDraftSource('typed');
                  }}
                  onSend={sendPayment}
                  onAnswerVoice={() => answer('voice')}
                  onAnswerChat={() => answer('chat')}
                  onDecline={finishDecline}
                  onSubmit={() => finishAnswer(draft, draftSource)}
                  onDemo={demoResponse}
                  onRetry={retry}
                  onCancel={cancelPayment}
                  onProceedAnyway={proceedAfterWarning}
                  onSwitchChat={switchToChat}
                  onSwitchVoice={switchToVoice}
                  onEnd={() => incomplete('Customer ended the verification call.', 'No answer')}
                  voiceSupported={voiceSupported}
                  voiceError={voiceError}
                  speaking={assistantSpeaking}
                  duration={duration}
                  muted={muted}
                  setMuted={setMuted}
                  micMuted={micMuted}
                  onMicMute={toggleMic}
                  demoResponses={demoResponses}
                  onSettings={() => setStage('settings')}
                  onNewPayment={() => setStage('form')}
                  trusted={trusted}
                  setTrusted={setTrusted}
                  consent={consent}
                  setConsent={setConsent}
                />
              </div>
            </div>
          ) : surface === 'Settings' ? (
            <Policies policyLimit={policyLimit} />
          ) : surface === 'Verification Sources' ? (
            <Sources records={records} />
          ) : surface === 'Agent Payments' ? (
            <AgentSurface
              agentResult={agentResult}
              setAgentResult={setAgentResult}
              merchant={agentMerchant}
              setMerchant={setAgentMerchant}
              category={agentCategory}
              setCategory={setAgentCategory}
              amount={agentAmount}
              setAmount={setAgentAmount}
            />
          ) : null}
          <footer
            style={{
              marginTop: 25,
              color: '#87939c',
              fontSize: 9,
              display: 'flex',
              justifyContent: 'space-between',
              gap: 10,
              flexWrap: 'wrap',
            }}
          >
            <span>AegisPay AI · Core Banking Simulator & Deterministic Risk Engine</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

type PhoneProps = {
  scenario: Scenario;
  stage: string;
  recipient: string;
  setRecipient: (v: string) => void;
  amount: number;
  setAmount: (v: number) => void;
  purpose: string;
  setPurpose: (v: string) => void;
  reference: string;
  setReference: (v: string) => void;
  tx: Tx | null;
  mode: Mode;
  question: string;
  questionIndex: number;
  questionsCount: number;
  draft: string;
  setDraft: (v: string) => void;
  onSend: () => void;
  onAnswerVoice: () => void;
  onAnswerChat: () => void;
  onDecline: () => void;
  onSubmit: () => void;
  onDemo: () => void;
  onRetry: () => void;
  onCancel: () => void;
  onProceedAnyway: () => void;
  onSwitchChat: () => void;
  onSwitchVoice: () => void;
  onEnd: () => void;
  voiceSupported: boolean;
  voiceError: string;
  speaking: boolean;
  duration: number;
  muted: boolean;
  setMuted: (v: boolean) => void;
  micMuted: boolean;
  onMicMute: () => void;
  demoResponses: boolean;
  onSettings: () => void;
  onNewPayment: () => void;
  trusted: boolean;
  setTrusted: (v: boolean) => void;
  consent: boolean;
  setConsent: (v: boolean) => void;
};

function CustomerPhone(p: PhoneProps) {
  const active = ['active', 'chat', 'processing'].includes(p.stage);
  const incoming = ['pending', 'ringing'].includes(p.stage);
  const mm = String(Math.floor(p.duration / 60)).padStart(2, '0');
  const ss = String(p.duration % 60).padStart(2, '0');

  return (
    <div className="phone-frame" data-testid="customer-phone">
      <div className="phone-screen">
        <div className="phone-statusbar">
          <span>9:41</span>
          <span>ASTER</span>
        </div>
        <div className="phone-appbar">
          <div className="phone-brand">
            <span className="brand-mark">A</span>Aster Bank
          </div>
          <button className="button small" onClick={p.onSettings} aria-label="Open safety settings" data-testid="phone-settings">
            <LockKeyhole />
          </button>
        </div>
        <div className={classes('phone-content', incoming && 'incoming-phone-content')} data-testid={`phone-stage-${p.stage}`}>
          {p.stage === 'home' && (
            <>
              <div className="phone-hero">
                <h3>Good afternoon, Anika</h3>
                <p>Everyday account · safely in your control.</p>
              </div>
              <div className="phone-panel">
                <h4>Available balance</h4>
                <div className="phone-amount">₹2,48,650</div>
                <button className="phone-action" onClick={p.onNewPayment} data-testid="phone-home-new">
                  New payment
                </button>
              </div>
            </>
          )}
          {incoming && (
            <>
              <div className="phone-hold-message" data-testid="money-unsent-banner">
                <strong>{fmt(p.tx?.amount ?? p.amount)} pending</strong>
                <span>Money has not been sent. It remains in your account.</span>
              </div>
              {p.stage === 'pending' ? (
                <div className="phone-panel">
                  <h4>Preparing payment verification</h4>
                  <div className="processing-steps">
                    <span className="processing-step done">Payment held</span>
                    <span className="processing-step active">Calling customer</span>
                    <span className="processing-step">Customer response</span>
                  </div>
                  <p>The incoming call will appear here shortly.</p>
                </div>
              ) : (
                <div className="call-screen incoming-call" data-testid="incoming-call-screen">
                  <div className="call-avatar ringing">
                    <span className="brand-mark">A</span>
                  </div>
                  <div className="card-kicker">PAYMENT VERIFICATION</div>
                  <h3 style={{ font: '700 18px var(--font-display)', margin: '7px 0 3px' }}>Aster Bank</h3>
                  <p className="subhead">Incoming call · attempt {p.tx?.attempt ?? 1}</p>
                  <div className="phone-panel call-payment-details">
                    <div className="phone-row">
                      <span>Amount</span>
                      <strong>{fmt(p.tx?.amount ?? p.amount)}</strong>
                    </div>
                    <div className="phone-row">
                      <span>Recipient</span>
                      <strong>{p.tx?.recipient ?? p.recipient}</strong>
                    </div>
                  </div>
                  <div className="call-actions">
                    <button className="call-choice decline" onClick={p.onDecline} data-testid="button-decline-call">
                      <span className="call-button">
                        <PhoneOff />
                      </span>
                      Decline
                    </button>
                    <button className="call-choice answer" onClick={p.onAnswerVoice} data-testid="button-answer-call">
                      <span className="call-button">
                        <PhoneIcon />
                      </span>
                      Answer
                    </button>
                  </div>
                  <button className="phone-secondary" onClick={p.onAnswerChat} data-testid="button-answer-in-chat">
                    <MessageSquareText size={13} />
                    Answer in chat
                  </button>
                  <p className="phone-mic">Microphone access starts only if you answer by voice.</p>
                </div>
              )}
            </>
          )}
          {p.stage === 'form' && (
            <>
              <div className="eyebrow">PAYMENTS</div>
              <h3 style={{ font: '700 18px var(--font-display)', marginBottom: 13 }}>Send money</h3>
              <div className="mini-form">
                <label>
                  <span className="field-label">Recipient</span>
                  <input
                    className="field-input"
                    value={p.recipient}
                    onChange={(e) => p.setRecipient(e.target.value)}
                    data-testid="phone-input-recipient"
                  />
                  <span className="recipient-hint">
                    {p.scenario === 'digital_arrest'
                      ? 'Govt Security Account · cbi.clearance@sbi'
                      : p.scenario === 'investment_scam'
                        ? 'Apex Yield · apexyield@icici'
                        : p.scenario === 'fake_invoice'
                          ? 'Starling Supplies · 9928172635@kotak'
                          : p.scenario === 'mule_network'
                            ? 'UPI ID · fastcash99@upi'
                            : 'Account ending •• 1880'}
                  </span>
                </label>
                <label>
                  <span className="field-label">Amount (₹)</span>
                  <input
                    type="number"
                    min="1"
                    className="field-input"
                    value={p.amount}
                    onChange={(e) => p.setAmount(Number(e.target.value))}
                    data-testid="phone-input-amount"
                  />
                </label>
                <label>
                  <span className="field-label">Note (optional)</span>
                  <textarea
                    className="field-textarea"
                    value={p.purpose}
                    onChange={(e) => p.setPurpose(e.target.value)}
                    placeholder="For example, rent or invoice"
                    data-testid="phone-input-purpose"
                  />
                </label>
                <button
                  className="phone-action"
                  onClick={p.onSend}
                  disabled={!p.recipient.trim() || p.amount <= 0}
                  data-testid="phone-send-money"
                >
                  Send money
                </button>
                <p className="phone-mic">Payment safety checks evaluate risk deterministically before any money is sent.</p>
              </div>
            </>
          )}
          {active && (
            <>
              <div className="call-screen" style={{ padding: '12px 2px 3px' }}>
                <div className="call-avatar">
                  <PhoneCall />
                </div>
                <span className="call-status">
                  <span className="online-dot" />
                  Connected · {mm}:{ss}
                </span>
                <h3 style={{ font: '700 15px var(--font-display)', margin: '10px 0 3px' }}>Aster Bank Verification</h3>
                <p className="phone-mic">Payment safety check</p>
                <div className="call-controls">
                  {p.stage === 'active' && (
                    <>
                      <button
                        className={classes('call-mute', p.micMuted && 'muted')}
                        onClick={p.onMicMute}
                        aria-label={p.micMuted ? 'Unmute microphone' : 'Mute microphone'}
                        data-testid="button-mute-microphone"
                      >
                        {p.micMuted ? <MicOff size={14} /> : <Mic size={14} />}
                      </button>
                      <button
                        className={classes('call-mute', p.muted && 'muted')}
                        onClick={() => p.setMuted(!p.muted)}
                        aria-label={p.muted ? 'Unmute assistant audio' : 'Mute assistant audio'}
                        data-testid="button-mute-audio"
                      >
                        {p.muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
                      </button>
                    </>
                  )}
                  {p.mode === 'voice' && (
                    <button className="button small" onClick={p.onSwitchChat} data-testid="button-switch-chat">
                      <MessageSquareText />
                      Switch to chat
                    </button>
                  )}
                  {p.mode === 'chat' && p.voiceSupported && (
                    <button className="button small" onClick={p.onSwitchVoice} data-testid="button-switch-voice">
                      <Mic />
                      Switch to voice
                    </button>
                  )}
                  <button className="button danger small" onClick={p.onEnd} data-testid="button-end-call">
                    <PhoneOff />
                    End call
                  </button>
                </div>
              </div>
              <div className="phone-panel">
                <div className="card-kicker">
                  QUESTION {Math.min(p.questionIndex + 1, p.questionsCount)} OF {p.questionsCount}
                </div>
                <h4 style={{ fontSize: 12, lineHeight: 1.4, marginTop: 5 }}>{p.question}</h4>
                <div className="processing-steps">
                  <span className={classes('processing-step', p.speaking ? 'active' : 'done')}>
                    {p.speaking ? 'Assistant speaking' : 'Question ready'}
                  </span>
                  <span
                    className={classes(
                      'processing-step',
                      p.stage === 'active' && !p.speaking && !p.voiceError && !p.micMuted ? 'active' : ''
                    )}
                  >
                    {p.mode === 'voice'
                      ? p.micMuted
                        ? 'Microphone muted'
                        : p.voiceError
                          ? 'Voice unavailable'
                          : p.speaking
                            ? 'Assistant speaking'
                            : 'Listening'
                      : 'Chat response'}
                  </span>
                  <span className={classes('processing-step', p.stage === 'processing' ? 'active' : '')}>
                    {p.stage === 'processing' ? 'Processing answer' : 'Transcript ready'}
                  </span>
                </div>
                <div className="transcript-feed" data-testid="phone-transcript">
                  {(p.tx?.statements ?? []).map((s, i) => (
                    <div className="transcript-line customer" key={`${i}-${s.answer}`}>
                      <b>
                        Your response · {s.source}
                      </b>
                      {s.answer}
                    </div>
                  ))}
                </div>
                {p.stage === 'processing' ? (
                  <div className="phone-alert" data-testid="phone-processing">
                    Processing your answer and checking against safety policies…
                  </div>
                ) : (
                  <label style={{ display: 'block', marginTop: 9 }}>
                    <span className="field-label">Your answer · review before sending</span>
                    <textarea
                      className="field-textarea"
                      value={p.draft}
                      onChange={(e) => p.setDraft(e.target.value)}
                      placeholder={
                        p.mode === 'voice'
                          ? 'Your recognized words appear here. Edit before submitting.'
                          : 'Type your answer here…'
                      }
                      data-testid="phone-answer-input"
                    />
                  </label>
                )}
                {p.voiceError && (
                  <div className="phone-alert" data-testid="voice-error">
                    {p.voiceError}
                    <button
                      className="button primary small"
                      style={{ marginTop: 8, width: '100%' }}
                      onClick={p.onSwitchChat}
                      data-testid="button-continue-in-chat"
                    >
                      Continue in chat
                    </button>
                  </div>
                )}
                {p.demoResponses && p.stage !== 'processing' && (
                  <button
                    className="button small"
                    style={{ marginTop: 8, width: '100%' }}
                    onClick={p.onDemo}
                    data-testid="button-demo-response"
                  >
                    <Check />
                    Insert example response (not speech)
                  </button>
                )}
                {p.stage !== 'processing' && (
                  <button
                    className="phone-action"
                    style={{ marginTop: 8 }}
                    disabled={!p.draft.trim()}
                    onClick={p.onSubmit}
                    data-testid="button-submit-answer"
                  >
                    Submit answer
                  </button>
                )}
                {p.mode === 'voice' && !p.voiceSupported && (
                  <button className="phone-secondary" onClick={p.onSwitchChat} data-testid="button-fallback-chat">
                    Continue in chat
                  </button>
                )}
                <p className="phone-mic">
                  {p.mode === 'voice'
                    ? 'Browser speech recognition only after answering. Recognition pauses while assistant audio plays.'
                    : 'Secure demo chat · no microphone permission requested.'}
                </p>
              </div>
            </>
          )}
          {p.stage === 'warning' && (
            <>
              <div className="outcome-banner warning" role="alert" data-testid="phone-safety-warning">
                <h3>Safety warning — review before choosing</h3>
                <p>{p.tx?.reason || 'This payment could not be confirmed.'}</p>
              </div>
              <div className="phone-panel">
                <h4>Money has not been sent</h4>
                <p>
                  {fmt(p.tx?.amount ?? p.amount)} to {p.tx?.recipient ?? p.recipient} remains held in your account.
                </p>
                <p style={{ marginTop: 9 }}>
                  Continue only if you independently recognize and trust this payment. This is a simulation; no real
                  money will move.
                </p>
                <div className="phone-decision-actions">
                  <button className="phone-action" onClick={p.onCancel} data-testid="button-cancel-warning">
                    Cancel payment
                  </button>
                  <button
                    className="phone-secondary phone-proceed"
                    onClick={p.onProceedAnyway}
                    data-testid="button-proceed-after-warning"
                  >
                    Proceed anyway
                  </button>
                </div>
              </div>
            </>
          )}
          {p.stage === 'incomplete' && (
            <>
              <div className="outcome-banner incomplete" data-testid="phone-incomplete">
                <h3>Verification incomplete — money was not sent.</h3>
                <p>{p.voiceError || p.tx?.reason || 'No answer was received. Payment remains unsent.'}</p>
              </div>
              <div className="phone-panel">
                <h4>Choose what to do next</h4>
                <button className="phone-action" onClick={p.onRetry} data-testid="button-retry-verification">
                  Retry verification
                </button>
                <button className="phone-secondary" onClick={p.onAnswerChat} data-testid="button-incomplete-chat">
                  Continue in chat
                </button>
                <button className="phone-secondary" onClick={p.onCancel} data-testid="button-cancel-incomplete">
                  Cancel payment
                </button>
              </div>
            </>
          )}
          {p.stage === 'outcome' && (
            <>
              <div
                className={classes(
                  'outcome-banner',
                  p.tx?.payment === 'Approved' || p.tx?.payment === 'Completed without check'
                    ? 'approved'
                    : p.tx?.payment === 'Cancelled'
                      ? 'cancelled'
                      : p.tx?.payment === 'Completed after warning'
                        ? 'warning'
                        : 'incomplete'
                )}
                data-testid="phone-final-outcome"
              >
                <h3>
                  {p.tx?.payment === 'Completed after warning'
                    ? 'Payment completed after warning'
                    : p.tx?.payment === 'Approved' || p.tx?.payment === 'Completed without check'
                      ? 'Payment approved'
                      : p.tx?.payment === 'Cancelled'
                        ? 'Payment cancelled'
                        : 'Payment complete'}
                </h3>
                <p>
                  {p.tx?.payment === 'Cancelled'
                    ? 'Money was not sent.'
                    : p.tx?.payment === 'Completed after warning'
                      ? 'You chose to continue after the warning. This simulation did not move real money.'
                      : p.tx?.payment === 'Approved' || p.tx?.payment === 'Completed without check'
                        ? 'Your simulated payment is complete. No real money moved.'
                        : p.tx?.reason}
                </p>
              </div>
              <div className="phone-panel">
                <h4>Payment receipt</h4>
                <div className="phone-row">
                  <span>Amount</span>
                  <strong>{fmt(p.tx?.amount ?? p.amount)}</strong>
                </div>
                <div className="phone-row">
                  <span>Recipient</span>
                  <strong>{p.tx?.recipient ?? p.recipient}</strong>
                </div>
                <div className="phone-row">
                  <span>Transaction</span>
                  <strong>{p.tx?.id ?? 'Local simulation'}</strong>
                </div>
                <p style={{ marginTop: 9 }}>{p.tx?.reason}</p>
              </div>
              <button
                className="phone-secondary"
                onClick={p.onCancel}
                disabled={p.tx?.payment !== 'Awaiting verification' && p.tx?.payment !== 'Verification incomplete'}
                data-testid="button-outcome-support"
              >
                <Headphones size={13} />
                Aster Bank support options
              </button>
            </>
          )}
          {p.stage === 'settings' && (
            <>
              <div className="eyebrow">PRIVACY & SAFETY</div>
              <h3 style={{ font: '700 18px var(--font-display)' }}>Safety settings</h3>
              <div className="settings-row">
                <span>Trusted contact · Maya R.</span>
                <button
                  aria-label="Toggle trusted contact"
                  className={classes('switch', p.trusted && 'on')}
                  onClick={() => p.setTrusted(!p.trusted)}
                  data-testid="toggle-phone-trusted"
                />
              </div>
              <div className="settings-row">
                <span>Allow limited safety alert</span>
                <button
                  aria-label="Toggle safety alert consent"
                  className={classes('switch', p.consent && 'on')}
                  onClick={() => p.setConsent(!p.consent)}
                  data-testid="toggle-phone-consent"
                />
              </div>
              <p className="simulation-note">Preview only. This prototype sends no notification.</p>
            </>
          )}
          {p.stage === 'agent' && (
            <div className="phone-panel">
              <h4>Agent payment</h4>
              <p>Secondary mandate demo. No payment is made.</p>
            </div>
          )}
        </div>
        <div className="phone-bottom">
          <div className="phone-nav">
            <span>
              <Landmark />
              Home
            </span>
            <span>
              <ArrowDownLeft />
              Payments
            </span>
            <span>
              <ShieldCheck />
              Safety
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function TransactionDrawer({
  tx,
  tab,
  setTab,
  onClose,
  onRetry,
  policyLimit,
}: {
  tx: Tx;
  tab: DrawerTab;
  setTab: (v: DrawerTab) => void;
  onClose: () => void;
  onRetry: () => void;
  policyLimit: number;
}) {
  const checks = [
    ['Institution', tx.claimInstitution || 'Not extracted'],
    ['Customer', tx.customer],
    ['Instruction', tx.claimInstruction || tx.purpose || 'Not extracted'],
    ['Recipient', tx.recipient],
    ['Amount', fmt(tx.amount)],
    ['Reference', tx.claimReference || tx.reference || 'Not supplied'],
  ];
  const verification = verificationStatus(tx);
  const callTone =
    verification === 'Complete'
      ? 'green'
      : ['Calling', 'Voice connected', 'Chat active', 'Checking claim'].includes(verification)
        ? 'amber'
        : verification === 'Incomplete'
          ? 'blue'
          : '';
  const visibleResult = tx.result === 'Not independently verifiable' ? 'Not applicable' : tx.result;

  const riskTier = tx.assessment?.risk_level ?? 'LOW';
  const riskTone =
    riskTier === 'CRITICAL'
      ? 'red'
      : riskTier === 'HIGH'
        ? 'amber'
        : riskTier === 'MEDIUM'
          ? 'blue'
          : 'green';

  return (
    <section className="detail-panel card" data-testid="transaction-drawer">
      <div className="detail-drawer">
        <div className="drawer-head">
          <div>
            <div className="card-kicker">SELECTED PAYMENT</div>
            <h2>
              {tx.customer} · {fmt(tx.amount)}
            </h2>
            <div className="mono">
              {tx.id} · {tx.customerId}
            </div>
            <span className={`pill ${callTone}`} style={{ marginTop: 9 }} data-testid="drawer-call-status">
              {verification === 'Not required' ? 'Not required' : `${verification} · attempt ${tx.attempt}`}
            </span>
          </div>
          <button className="button small" onClick={onClose} aria-label="Close transaction details" data-testid="button-close-drawer">
            <X />
          </button>
        </div>
        <div className="drawer-facts">
          <div>
            <small>RECIPIENT</small>
            <strong>{tx.recipient}</strong>
          </div>
          <div>
            <small>PAYMENT STATUS</small>
            <strong data-testid="drawer-payment-status">{paymentStatus(tx)}</strong>
          </div>
          <div>
            <small>RISK EVALUATION</small>
            <strong data-testid="drawer-risk-level">
              <span className={`pill ${riskTone}`} style={{ marginLeft: 0 }}>
                {tx.assessment ? `${tx.assessment.risk_level} (${tx.assessment.risk_score}/100)` : 'Assessing…'}
              </span>
            </strong>
          </div>
          <div>
            <small>INITIATED</small>
            <strong>{tx.initiated}</strong>
          </div>
        </div>
        <div className="tabrow">
          {(['Live verification', 'Risk assessment', 'Evidence & checks', 'Decision & history'] as const).map((t) => (
            <button
              key={t}
              className={classes('tab', tab === t && 'active')}
              onClick={() => setTab(t)}
              data-testid={`drawer-tab-${t.toLowerCase().replaceAll(' ', '-').replace('&', 'and')}`}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === 'Live verification' && (
          <>
            <section className="drawer-section">
              <h3>Live verification</h3>
              <div className="phone-row">
                <span>Current processing step</span>
                <strong>{tx.process}</strong>
              </div>
              <div className="processing-steps">
                <span className={classes('processing-step', tx.payment !== 'Awaiting verification' && 'done')}>
                  Payment received
                </span>
                <span className={classes('processing-step', ['Calling', 'Connected', 'In progress'].includes(tx.call) ? 'active' : 'done')}>
                  Customer verification
                </span>
                <span className={classes('processing-step', tx.result !== 'Not independently verifiable' ? 'done' : '')}>
                  Claim verification
                </span>
                <span
                  className={classes(
                    'processing-step',
                    tx.payment === 'Awaiting customer decision'
                      ? 'active'
                      : ['Approved', 'Cancelled', 'Completed after warning', 'Completed without check'].includes(tx.payment)
                        ? 'done'
                        : ''
                  )}
                >
                  Decision
                </span>
              </div>
              <div className="live-claim-summary" data-testid="live-claim-summary">
                <div>
                  <small>CLAIM</small>
                  <strong>{tx.claim || 'No claim extracted yet.'}</strong>
                </div>
                <div>
                  <small>INDEPENDENT CHECK</small>
                  <strong>{visibleResult}</strong>
                </div>
              </div>
              <div className="why-checked">
                <span>Why this was checked</span>
                <strong>{checkReason(tx, policyLimit)}</strong>
              </div>
            </section>
            <section className="drawer-section">
              <h3>Conversation</h3>
              <div className="transcript-feed" data-testid="drawer-transcript">
                {tx.statements.length ? (
                  tx.statements.map((s, i) => (
                    <div key={i} className="transcript-line customer">
                      <b>
                        Customer · {s.source} · {s.question}
                        <time>{s.at || tx.initiated}</time>
                      </b>
                      {s.answer}
                    </div>
                  ))
                ) : (
                  <div className="transcript-line assistant">
                    <b>Session</b>Conversation will appear when the customer answers.
                  </div>
                )}
              </div>
            </section>
            {tx.payment === 'Verification incomplete' && (
              <button className="button primary" onClick={onRetry} data-testid="drawer-retry">
                <RotateCcw />
                Retry same transaction
              </button>
            )}
          </>
        )}

        {tab === 'Risk assessment' && (
          <section className="drawer-section" data-testid="drawer-risk-section">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Deterministic Risk Assessment</h3>
              <span
                className={`pill ${tx.assessment?.source === 'demo_fallback' ? 'amber' : 'green'}`}
                data-testid="assessment-source-badge"
                style={{ fontSize: 10, fontWeight: 600 }}
              >
                {tx.assessment?.source === 'demo_fallback' ? 'Demo Fallback (Offline Mode)' : 'Live Backend Assessment'}
              </span>
            </div>

            {tx.assessment?.source === 'demo_fallback' && (
              <div className="notice amber" style={{ margin: '0 0 12px 0' }} data-testid="assessment-fallback-banner">
                <ShieldAlert size={14} style={{ flex: 'none', marginTop: 1 }} />
                <span>
                  <strong>Demo Mode Fallback:</strong> The backend API is unreachable. This score was evaluated
                  locally using deterministic policy rules for demonstration purposes.
                </span>
              </div>
            )}

            <div className="payment-summary" style={{ gridTemplateColumns: '1.2fr 1fr 1fr' }}>
              <div className="metric">
                <div className="metric-label">RISK SCORE</div>
                <div className="metric-value amount">
                  {tx.assessment?.risk_score ?? 0}
                  <span style={{ fontSize: 11, color: '#8895a0' }}> / 100</span>
                </div>
              </div>
              <div className="metric">
                <div className="metric-label">RISK LEVEL</div>
                <div className="metric-value">
                  <span className={`pill ${riskTone}`} data-testid="drawer-risk-tier">
                    {tx.assessment?.risk_level ?? 'LOW'}
                  </span>
                </div>
              </div>
              <div className="metric">
                <div className="metric-label">RECOMMENDED ACTION</div>
                <div className="metric-value" style={{ fontSize: 11, fontWeight: 700 }} data-testid="drawer-recommended-action">
                  {tx.assessment?.recommended_action ?? 'ALLOW'}
                </div>
              </div>
            </div>

            <div className="notice" style={{ marginTop: 10 }}>
              <ShieldAlert size={15} style={{ flex: 'none', marginTop: 1 }} />
              <div>
                <strong>Policy Recommendation: </strong>
                <span>{tx.assessment?.explanation || 'Simulated transaction evaluated within baseline parameters.'}</span>
              </div>
            </div>

            <h4 style={{ fontSize: 12, fontWeight: 700, margin: '16px 0 8px' }}>
              Triggered Deterministic Rules ({tx.assessment?.triggered_rules.length ?? 0})
            </h4>
            {tx.assessment?.triggered_rules && tx.assessment.triggered_rules.length > 0 ? (
              <div style={{ display: 'grid', gap: 8 }} data-testid="triggered-rules-list">
                {tx.assessment.triggered_rules.map((rule) => {
                  const ruleTone =
                    rule.severity === 'CRITICAL'
                      ? 'red'
                      : rule.severity === 'HIGH'
                        ? 'amber'
                        : rule.severity === 'MEDIUM'
                          ? 'blue'
                          : 'green';
                  return (
                    <div className="evidence" key={rule.rule_id} style={{ padding: 10 }}>
                      <div className="evidence-top">
                        <span className="evidence-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <code>{rule.rule_id}</code> · {rule.rule_name}
                        </span>
                        <span className={`pill ${ruleTone}`}>
                          {rule.weight > 0 ? `+${rule.weight}` : rule.weight} pts · {rule.severity}
                        </span>
                      </div>
                      <p style={{ margin: '4px 0 2px', color: '#203044', fontWeight: 500 }}>{rule.evidence}</p>
                      <p style={{ fontSize: 9, color: '#7a8996', margin: 0 }}>{rule.description}</p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="subhead">No risk rules triggered. Clean transaction features.</p>
            )}

            <h4 style={{ fontSize: 12, fontWeight: 700, margin: '16px 0 8px' }}>Supporting Evidence Findings</h4>
            {tx.assessment?.supporting_evidence && tx.assessment.supporting_evidence.length > 0 ? (
              <ul
                style={{ margin: 0, paddingLeft: 18, fontSize: 11, color: '#384856', lineHeight: 1.6 }}
                data-testid="supporting-evidence-list"
              >
                {tx.assessment.supporting_evidence.map((ev, i) => (
                  <li key={i}>{ev}</li>
                ))}
              </ul>
            ) : (
              <p className="subhead">No adverse signals recorded.</p>
            )}

            {tx.assessment?.missing_evidence && tx.assessment.missing_evidence.length > 0 && (
              <>
                <h4 style={{ fontSize: 12, fontWeight: 700, margin: '16px 0 8px', color: '#8b6410' }}>
                  Missing / Unobserved Telemetry ({tx.assessment.missing_evidence.length})
                </h4>
                <div className="notice info" style={{ margin: '4px 0 8px' }}>
                  <span>
                    <strong>Deterministic Guardrail:</strong> Unobserved signals remain explicitly unknown and are never
                    assumed to be either safe or suspicious.
                  </span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }} data-testid="missing-evidence-list">
                  {tx.assessment.missing_evidence.map((field) => (
                    <span className="pill blue" key={field}>
                      ⚠️ {field}: Unknown
                    </span>
                  ))}
                </div>
              </>
            )}
          </section>
        )}

        {tab === 'Evidence & checks' && (
          <>
            <section className="drawer-section">
              <h3>Customer statements</h3>
              {tx.statements.length ? (
                tx.statements.map((s, i) => (
                  <div className="evidence" style={{ marginBottom: 8 }} key={i}>
                    <div className="evidence-top">
                      <span className="evidence-label">{s.question}</span>
                      <span className="pill blue">{s.at || tx.initiated}</span>
                    </div>
                    <p>“{s.answer}”</p>
                  </div>
                ))
              ) : (
                <p className="subhead">No submitted statements.</p>
              )}
            </section>
            <section className="drawer-section">
              <h3>Extracted claim · distinct from interpretation</h3>
              <p>{tx.claim || 'No claim extracted yet.'}</p>
              <div className="evidence-grid">
                <EvidenceBox
                  title="Customer statement"
                  tone="blue"
                  copy={tx.statements.map((s) => s.answer).join(' ') || 'No customer statement submitted.'}
                />
                <EvidenceBox
                  title="System inference"
                  tone={tx.concern ? 'amber' : 'blue'}
                  copy={
                    tx.concern
                      ? 'Potential pressure or safe-account indicators reported. Indicators are not a determination by themselves.'
                      : 'No urgency, secrecy, or safe-account indicator extracted.'
                  }
                />
              </div>
            </section>
            <section className="drawer-section">
              <h3>Independent source · Aster Bank instruction registry</h3>
              <p className="subhead">Caller-provided phone numbers and websites are never used as verification evidence.</p>
              <span
                className={`pill ${
                  tx.result === 'Confirmed'
                    ? 'green'
                    : tx.result === 'Contradicted'
                      ? 'red'
                      : tx.result === 'Source unavailable'
                        ? 'blue'
                        : 'amber'
                }`}
                data-testid="verification-result"
              >
                {visibleResult}
              </span>
              <div className="page-content-table" style={{ marginTop: 10 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Claim checked</th>
                    </tr>
                  </thead>
                  <tbody>
                    {checks.map(([a, b]) => (
                      <tr key={a}>
                        <td>{a}</td>
                        <td>{b}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="decision-note" style={{ marginTop: 10 }}>
                A missing record is not proof of fraud.
              </p>
            </section>
          </>
        )}

        {tab === 'Decision & history' && (
          <>
            <section className="drawer-section">
              <h3>Final decision</h3>
              <div className="decision-outcome-summary">
                <div>
                  <small>DECISION</small>
                  <strong>{decisionStatus(tx)}</strong>
                </div>
                <div>
                  <small>PAYMENT</small>
                  <strong data-testid="decision-payment-status">{paymentStatus(tx)}</strong>
                </div>
              </div>
              <p style={{ marginTop: 12 }} data-testid="decision-reason">
                {tx.reason}
              </p>
              <div className="mono">
                Claim result: {visibleResult} · Decision timestamp: {tx.audit[0]?.at ?? 'Pending'}
              </div>
            </section>
            <section className="drawer-section">
              <h3>Timestamped audit events</h3>
              <div className="timeline" data-testid="audit-timeline">
                {tx.audit.map((a, i) => (
                  <div className="timeline-row" key={`${a.at}-${i}`}>
                    <div className="timeline-dot" />
                    <div>
                      <div className="timeline-title">{a.title}</div>
                      <div className="timeline-copy">{a.detail}</div>
                    </div>
                    <time className="timeline-time">{a.at}</time>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </section>
  );
}

function EvidenceBox({ title, copy, tone }: { title: string; copy: string; tone: 'green' | 'amber' | 'red' | 'blue' }) {
  return (
    <div className="evidence">
      <div className="evidence-top">
        <span className="evidence-label">{title}</span>
        <span className={`pill ${tone}`}>{title === 'Customer statement' ? 'SOURCE' : 'INFERENCE'}</span>
      </div>
      <p>{copy}</p>
    </div>
  );
}

function Policies({ policyLimit }: { policyLimit: number }) {
  const rules = [
    'Known recipient and routine payments do not require additional questions.',
    'Unfamiliar recipients trigger customer verification. Amounts above the review threshold are marked as unusual; amount alone is not a fraud determination.',
    'Safe-account language combined with urgency or secrecy, or a mismatched instruction with pressure indicators, shows a warning. The customer chooses whether to cancel or proceed.',
    'A claim is confirmed only when customer, institution, instruction, recipient, amount and reference match.',
    'A missing record alone is not proof of fraud. If the instruction source is unavailable, the payment remains unsent and verification is incomplete.',
    'Staff can inspect evidence and history; they cannot manually release a customer payment.',
  ];
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">PREFERENCES · PAYMENT SAFETY</div>
          <h1>Settings</h1>
          <p className="subhead">Read-only overview of the checks used in this prototype.</p>
        </div>
      </div>
      <div className="console-grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 330px' }}>
        <section className="card">
          <div className="card-pad">
            <div className="card-head">
              <h2 className="card-title">Payment safety policy</h2>
            </div>
            {rules.map((r, i) => (
              <div className="policy-rule" key={r} data-testid={`policy-rule-${i}`}>
                <div className="rule-num">0{i + 1}</div>
                <div className="rule-text">{r}</div>
              </div>
            ))}
          </div>
        </section>
        <div className="stack">
          <section className="card">
            <div className="card-pad">
              <div className="card-kicker">REVIEW THRESHOLD</div>
              <div className="settings-value">{fmt(policyLimit)}</div>
              <p className="subhead">New-recipient payments at or above this amount are marked as unusual.</p>
            </div>
          </section>
          <section className="card">
            <div className="card-pad">
              <div className="card-kicker">WHEN A SOURCE IS UNAVAILABLE</div>
              <p className="settings-value">Payment held</p>
              <p className="subhead">Verification stays incomplete. The system does not approve or send the payment.</p>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

function Sources({ records }: { records: Tx[] }) {
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">VERIFICATION · LOCAL REGISTRY</div>
          <h1>Verification Sources</h1>
          <p className="subhead">Narrow declared coverage. No phone, web, government or third-party lookup.</p>
        </div>
        <span className="pill blue">
          <LockKeyhole size={12} />
          LOCAL ONLY
        </span>
      </div>
      <section className="card">
        <div className="card-pad">
          <div className="card-head">
            <h2 className="card-title">Aster Bank demo instruction registry</h2>
            <span className="pill green">SIMULATED FIXTURE</span>
          </div>
          <p className="subhead">
            Local fixtures only; not a real external verification. Record comparison uses institution, customer, requested
            action, recipient, amount and reference.
          </p>
          <div className="source-row">
            <div className="source-icon">
              <Landmark />
            </div>
            <div>
              <div className="source-name">Aster Bank · authenticated instruction registry</div>
              <div className="source-detail">Available in this local prototype; scenario can simulate a source outage.</div>
            </div>
            <span className="pill green">LOCAL</span>
          </div>
          <div className="source-row">
            <div className="source-icon">
              <Smartphone />
            </div>
            <div>
              <div className="source-name">Phone numbers and websites</div>
              <div className="source-detail">Not queried, monitored or used as verification evidence.</div>
            </div>
            <span className="pill blue">OUT OF SCOPE</span>
          </div>
          <h3 style={{ font: '700 12px var(--font-display)', marginTop: 16 }}>Configured sample records</h3>
          <div className="page-content-table">
            <table>
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Customer</th>
                  <th>Institution</th>
                  <th>Instruction</th>
                  <th>Recipient</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                <tr data-testid="registry-record-1">
                  <td>ASB-48219</td>
                  <td>Anika Rao</td>
                  <td>Aster Bank</td>
                  <td>Settlement transfer</td>
                  <td>Aster Bank Settlement</td>
                  <td>₹6,500</td>
                </tr>
                <tr data-testid="registry-record-2">
                  <td>ASB-48220</td>
                  <td>Arjun Nair</td>
                  <td>Aster Bank</td>
                  <td>Account fee</td>
                  <td>Aster Bank Fees</td>
                  <td>₹1,250</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mono" style={{ marginTop: 12 }}>
            Current records shown: {records.length} · synthetic payment queue only.
          </p>
        </div>
      </section>
    </>
  );
}

function AgentSurface({
  agentResult,
  setAgentResult,
  merchant,
  setMerchant,
  category,
  setCategory,
  amount,
  setAmount,
}: {
  agentResult: 'idle' | 'approved' | 'rejected';
  setAgentResult: (v: 'idle' | 'approved' | 'rejected') => void;
  merchant: string;
  setMerchant: (v: string) => void;
  category: string;
  setCategory: (v: string) => void;
  amount: string;
  setAmount: (v: string) => void;
}) {
  const [history, setHistory] = useState<Audit[]>([]);
  function check() {
    const allowed = merchant === 'Orchid Audio' && category === 'Headphones' && Number(amount) <= 5000;
    setAgentResult(allowed ? 'approved' : 'rejected');
    setHistory((old) => [
      makeAudit(
        allowed ? 'Mandate allowed' : 'Mandate rejected',
        allowed ? 'Merchant, category and amount are within local mandate.' : 'Attempt is outside the declared local mandate.'
      ),
      ...old,
    ]);
  }
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">AUTONOMOUS PAYMENT · SECONDARY DEMO</div>
          <h1>Agent Payments</h1>
          <p className="subhead">A narrow local mandate check. Separate from the primary customer safety workflow.</p>
        </div>
        <span className="pill amber">SIMULATION ONLY</span>
      </div>
      <div className="console-grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 330px' }}>
        <div className="stack">
          <section className="card">
            <div className="card-pad">
              <div className="agent-hero">
                <strong>Agent mandate · AGENT-007</strong>
                <p>Allowed: Headphones · Orchid Audio · up to ₹5,000 · one-time. No purchase is executed.</p>
              </div>
              <div className="field-row">
                <label>
                  <span className="field-label">Merchant</span>
                  <select className="select" value={merchant} onChange={(e) => setMerchant(e.target.value)} data-testid="agent-merchant">
                    <option>Other merchant</option>
                    <option>Orchid Audio</option>
                  </select>
                </label>
                <label>
                  <span className="field-label">Category</span>
                  <select className="select" value={category} onChange={(e) => setCategory(e.target.value)} data-testid="agent-category">
                    <option>Gift cards</option>
                    <option>Headphones</option>
                  </select>
                </label>
              </div>
              <label style={{ display: 'block', marginTop: 12 }}>
                <span className="field-label">Amount · ₹</span>
                <input
                  className="field-input"
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  data-testid="agent-amount"
                />
              </label>
              <button className="button primary" style={{ marginTop: 12 }} onClick={check} data-testid="button-check-mandate">
                <ShieldCheck />
                Check mandate
              </button>
            </div>
          </section>
          <section className="card">
            <div className="card-pad">
              <h2 className="card-title">Decision record</h2>
              <p className="subhead" style={{ marginTop: 10 }} data-testid="agent-result">
                {agentResult === 'idle'
                  ? 'Not evaluated'
                  : agentResult === 'approved'
                    ? 'Allowed by local mandate. No purchase was made.'
                    : 'Rejected by local mandate. No purchase was made.'}
              </p>
            </div>
          </section>
        </div>
        <section className="card">
          <div className="card-pad">
            <div className="card-kicker">ATTEMPT HISTORY</div>
            <div style={{ marginTop: 14 }}>
              {history.length ? (
                history.map((a, i) => (
                  <div className="timeline-row" key={i}>
                    <div className="timeline-dot" />
                    <div>
                      <div className="timeline-title">{a.title}</div>
                      <div className="timeline-copy">{a.detail}</div>
                    </div>
                    <time className="timeline-time">{a.at}</time>
                  </div>
                ))
              ) : (
                <p className="subhead">No mandate checks yet.</p>
              )}
            </div>
            <button
              className="button small"
              onClick={() => {
                setMerchant('Orchid Audio');
                setCategory('Headphones');
                setAmount('4500');
                setAgentResult('idle');
              }}
              data-testid="button-load-approved-example"
            >
              <Check />
              Load allowed example
            </button>
          </div>
        </section>
      </div>
    </>
  );
}

export default App;
