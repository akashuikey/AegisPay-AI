# ADR-008: Dynamic Gemini-Powered Simulated Voice and Chat Dialogue (Option A)

- **Status**: Accepted
- **Date**: 2026-10-18
- **Deciders**: Senior Architect / Full-Stack Engineer (Option A)

---

## Context and Problem Statement

Earlier milestones implemented deterministic risk scoring (P1-A3), AI forensic investigation (P2-A1/A2), deterministic decision policy (P2-A4), customer verification (P2-A5), coercion detection (P2-A6), and automated response orchestration (P2-A7). However, the customer interaction during simulated voice calls and chats in the phone preview remained scripted: a static three-question sequence (`initialQuestions`) and hardcoded regex branches evaluated locally in the frontend.

To realistically demonstrate and exercise AegisPay AI's full capabilities, the customer interaction must be dynamic, evidence-grounded, and multi-turn, driven by Gemini while upholding core system invariants.

### Constraints and Principles

1. **Deterministic Authority**: Gemini never directly alters transaction state or bypasses deterministic safeguards. All transactional outcomes (ALLOW, REQUIRE_VERIFICATION, HOLD_FOR_INVESTIGATION, BLOCK) remain strictly under the control of the deterministic policy engine and state machine.
2. **Adversarial Prompt-Injection Defense**: Customer speech and chat inputs are treated as untrusted data. They are isolated inside protective XML boundaries (`<untrusted_customer_response>`, `<untrusted_dialogue_history>`) with explicit system instructions prohibiting instruction overrides or security policy bypass.
3. **Voice Stress Advisory Rule**: Voice stress and phonetic anomalies are purely advisory and cannot independently justify adverse transaction outcomes (`VOICE_STRESS_ALONE_NON_DISQUALIFYING`).
4. **Finite, Bounded Dialogue**: Inquiries are capped at a maximum turn budget (default 6 customer turns) to prevent conversational drift, resource exhaustion, or denial-of-service.
5. **Session Isolation & Authentication**: Call sessions are authenticated via either an active operator JWT or a customer verification session token, preventing unauthorized access across transactions.
6. **Pure Simulation**: Zero external telephony (Twilio/PSTN) or real payment rails. All audio is rendered via the browser's Web Speech API and backend mock/Vertex Gemini endpoints.

---

## Decision

### 1. Domain Modeling (`app/domain/customer_dialogue.py`)
- Defined channels (`VOICE_SIMULATED`, `CHAT_SIMULATED`), directions (`OUTBOUND_SIMULATED`, `INBOUND_SIMULATED`), and lifecycle statuses (`INITIATED`, `RINGING`, `CONNECTED`, `COMPLETED`, `DECLINED`, `TIMED_OUT`, `FAILED`, `CANCELLED`).
- Structured turn results (`CustomerDialogueTurnResult`) returning:
  - `assistant_inquiry`: The next dynamically synthesized conversational question.
  - `internal_observations`: Evidence findings recorded for bank forensic logs.
  - `uncertainty_notes`: Missing or ambiguous facts.
  - `suggested_action`: Next recommended investigative step.
  - `is_terminal_turn`: Boolean flag indicating conversational conclusion.
  - `risk_sentiment` and `coercion_cues`: Authority impersonation, urgent transfer, secrecy demands, etc.
- Added `CUSTOMER = "customer"` to `ConversationRole` (`app/domain/investigation.py`) to unify dialogue turns under the conversation domain.

### 2. AI Client Layer (`app/services/ai_client.py`)
- Added `generate_customer_dialogue_turn` to the `AIInvestigationClient` protocol.
- Implemented in `VertexGeminiClient` with strict JSON schema enforcement, model latency tracking, and automatic retry on transient Gemini failures.
- Implemented dynamic synthesis in `MockGeminiClient` covering authority duress (CBI/police arrest threats), high-yield investment scams, supplier invoice mismatches, prompt-injection defense, and routine commercial transfers.

### 3. Persistence & Concurrency (`app/db/models.py`, Migration `0013`)
- Created `TransactionCallSessionModel` storing call metadata, attempt counts, channel, masked phone numbers, duration, failure reasons, and optimistic concurrency versioning.
- Added `conversation_type` to `InvestigationConversationModel` with default `"investigation"` and support for `"customer_dialogue"`.
- Linked each call session to an `InvestigationConversationModel` to preserve the full audit trail of dialogue turns.
- Applied eager loading (`selectinload`) and scalar attribute caching before commits to prevent async SQLAlchemy `MissingGreenlet` errors (SEC-01 compliance).

### 4. Application Service (`app/services/customer_dialogue_service.py`)
- Orchestrates the full lifecycle: `initiate_call_session`, `connect_call_session`, `submit_turn`, `complete_call_session`, `decline_call_session`.
- Enforces turn budget limits and handles idempotency via client-provided keys.
- On session completion, automatically triggers `CoercionService.analyze_transaction_coercion` on the accumulated transcript, linking the resulting analysis to the call session and transaction.

### 5. API Endpoints (`app/api/customer_dialogue.py`)
- Mounted under `/api/v1/transactions/{id}/calls` and `/api/v1/calls/{id}/*`.
- Secured via `authorize_call_access`, accepting either operator JWTs or customer verification session tokens.
- Fully typed request and response schemas (`app/schemas/customer_dialogue.py`).

### 6. Frontend Integration (`frontend/src/api/customerDialogueApi.ts`, `frontend/src/App.tsx`)
- Created typed client bindings for call session operations.
- Wired payment submission to initiate simulated call sessions on the backend and update the customer phone preview.
- Connected customer speech/chat turns to submit dialogue turns and dynamically speak or display Gemini's next question.
- Maintained seamless local fallback progression if the backend is unreachable.
- Added comprehensive unit and integration tests (`CustomerDialogue.test.tsx`).

---

## Consequences

### Positive
- Replaced static, hardcoded scripts with context-aware, evidence-rich customer dialogue.
- Full provenance and internal forensic observations are captured for bank audit trails.
- Coercion analysis is automatically triggered from actual conversation transcripts upon call completion.
- Robust error handling and offline demo compatibility remain preserved.

### Negative / Trade-offs
- Requires Gemini API quota in live provider mode; handled by deterministic offline `MockGeminiClient` fallback.
- Audio synthesis in browser depends on Web Speech API availability; graceful fallback to typed chat is supported.

---

## Addendum: Reliability & Security Hardening (P2-A10 audit)

A post-implementation reliability audit fixed the following confirmed defects while
preserving the decisions above:

1. **One active session per transaction** is now atomic at the database layer via a
   PostgreSQL partial unique index (`uq_call_sessions_active_tx` over `transaction_id`
   where `status IN ('INITIATED','RINGING','CONNECTED')`), replacing reliance on a
   read-before-write guard alone. Initiation persists the session first and resolves a
   losing concurrent race by returning the winning session.
2. **Recoverable initiation failure**: if the opening Gemini turn cannot be generated,
   the session is marked terminal `FAILED` (and its conversation closed) instead of being
   left as a permanently active, turn-less session, so a retry starts fresh.
3. **Terminal-state integrity**: completion is idempotent on `COMPLETED` but never
   rewrites another terminal state (`DECLINED`/`TIMED_OUT`/`FAILED`/`CANCELLED`) into
   `COMPLETED`.
4. **Turn-index races** surface as HTTP 409 (repositories roll back and re-raise
   `IntegrityError` on the existing `(conversation_id, turn_index)` constraint).
5. **Coercion analysis** is triggered from the full accumulated transcript (not only the
   final assistant turn) on **both** automatic and manual completion via a single shared
   path; its failure is isolated and never mutates transaction state. Deterministic policy
   remains the sole authority; voice stress remains advisory.
6. **Authorization**: customer verification tokens are enforced to their bound
   `transaction_id` (preventing cross-transaction access), and internal forensic fields are
   redacted from customer responses and returned only to operators.
7. **Frontend idempotency**: dialogue turns carry a per-answer `client_turn_id` and are
   guarded against duplicate in-flight submissions.

`TIMED_OUT` remains a reserved status: there is no server-side timeout sweeper; the
dialogue is bounded by a maximum turn budget (`MAX_DIALOGUE_TURNS`) and by client-driven
decline/complete actions.

---

## Addendum: Real-Time Gemini Live Voice (P2-A11)

The turn-based, text-generated voice path (browser STT → text Gemini → browser TTS) is
upgraded to **true bidirectional real-time audio** via the Gemini Live API, behind the
`GEMINI_LIVE_ENABLED` flag. The simulated text/chat dialogue remains the default and the
fallback.

- **Transport**: an authenticated WebSocket `WS /api/v1/calls/{id}/live`. The browser
  streams 16 kHz PCM16 microphone audio; the backend relays to Gemini Live and streams
  24 kHz PCM16 audio plus transcription/events back. **The Gemini API key never leaves the
  server** — the browser authenticates with its existing operator/customer token, and
  customer tokens are transaction-scoped (no cross-transaction streams).
- **Provider abstraction**: `LiveVoiceClient`/`LiveVoiceSession` with a real
  `GeminiLiveVoiceClient` (official `google-genai` Live API: audio in/out transcription,
  configurable model/voice, session resumption, context-window compression) and a
  deterministic mock for tests/offline.
- **Streaming transcript + parallel analysis**: an orchestrator runs independent,
  bounded, cancellable tasks. A single writer persists only final segments with a
  monotonic `seq` (`call_transcript_segments`, unique `(call_session_id, seq)`), deduping
  reconnect/replay; interim partials stream to the UI only. A separate analyzer produces a
  versioned (`live-analysis-v1`), transcript-grounded `LiveEvidenceSnapshot`
  (`call_live_analyses`) on its own cadence, without blocking audio and without overlapping
  itself. Analysis failure degrades to "unavailable" and never interrupts voice.
- **Invariants preserved**: the transcript/analysis workers never change transaction or
  call state — only the deterministic policy/state machine does. Analysis is advisory;
  voice stress/emotion is never an input to it; escalation requires combined, grounded
  markers. The conversational agent is dynamic (no scenario scripts), non-accusatory, and
  never reads internal scores/rules.
- **Resilience & limits**: bounded session duration, audio frame size, queue depth, one
  live session per call, and a process-wide concurrency cap; GoAway/resumption handles are
  captured per call; deterministic cancellation and provider-session close on termination.

**Verification scope**: the real Gemini Live integration is exercised against the mock
provider in automated tests; a real-provider handshake runs only via
`GEMINI_LIVE_SMOKE=1` with credentials. This remains a simulated prototype — no real
telephony or payment execution.

