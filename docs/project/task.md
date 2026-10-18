# Project Task Tracker: AegisPay AI

## Implementation Roadmap Overview

| Phase | Description | Status |
| :--- | :--- | :--- |
| **Phase 1** | **Core Banking Simulator & Deterministic Risk Engine** | `DONE` |
| **Phase 2** | **AI Investigation Agent & Multi-Modal Context Analysis** | `IN_PROGRESS` |
| **Phase 3** | **Customer Portal & Dynamic Intervention UI** | `NOT_STARTED` |
| **Phase 4** | **Fraud Operations Case Management & Audit Console** | `NOT_STARTED` |
| **Phase 5** | **End-to-End Scenarios, Hardening & Demonstration** | `NOT_STARTED` |

---

## Detailed Task Breakdown

### Phase 1: Repository Foundation & Transaction Domain Core

#### Task P1-A1: AegisPay AI Repository Foundation
- **Owner / Agent**: Senior Architect / Full-Stack Engineer (Agent 1)
- **Status**: `DONE`
- **Objective**: Establish the production-grade monorepo foundation, FastAPI backend, React/Vite frontend, PostgreSQL container setup, typed settings, Alembic migrations, health checks, testing baseline, persistent documentation, and preserved prototype UI.
- **Deliverables**:
  1. Monorepo folder layout (`backend/`, `frontend/`, `docs/`, `compose.yaml`, `Makefile`, `.github/`).
  2. FastAPI async backend with `/health/live` and `/health/ready` endpoints.
  3. React + TypeScript frontend with live backend connectivity indicator and full Aster Bank operations console + mobile simulator.
  4. Docker Compose with PostgreSQL 16 Alpine container and health check.
  5. Alembic async migration configuration (`0001_initial_baseline`).
  6. Unit and integration tests for backend (12 tests) and frontend (7 tests).
  7. Automated linting (Ruff, ESLint), formatting, and type checks (mypy, tsc).
  8. CI workflow in `.github/workflows/ci.yml`.
  9. Project governance docs (`prd.md`, `architecture.md`, `rules.md`, `task.md`, `memory.md`).
- **Acceptance Criteria**:
  - [x] Repository structure created matching specification.
  - [x] Backend starts cleanly and passes all tests (12/12 pytest passed).
  - [x] Frontend starts cleanly and connects to backend health check (verified via live probe badge & test).
  - [x] PostgreSQL runs in Docker Compose with health check (`aegispay_postgres` healthy).
  - [x] Alembic migration executes without error (`0001_initial_baseline` applied).
  - [x] Backend tests pass (`pytest` 12 passed in 0.04s).
  - [x] Backend linters and typecheck pass (`ruff check`, `ruff format`, `mypy` 0 errors).
  - [x] Frontend linters and typecheck pass (`eslint`, `tsc`, `vitest` 0 errors, 7 tests passed).
  - [x] Zero committed secrets, zero real external banking dependencies.
- **Verification Commands & Results**:
  ```bash
  # Docker
  docker compose up -d db                    # Status: Healthy on 127.0.0.1:5433

  # Backend
  cd backend
  uv sync --dev                              # Resolved 46 packages
  uv run alembic upgrade head                # Applied 0001_initial_baseline
  uv run pytest                              # 12 passed in 0.04s
  uv run ruff check .                        # All checks passed
  uv run ruff format --check .               # 23 files already formatted
  uv run mypy app                            # Success: no issues found in 15 source files

  # Frontend
  cd ../frontend
  npm run lint                               # 0 errors, 0 warnings
  npm run typecheck                          # 0 errors
  npm run test                               # 7 passed in 2 test files
  npm run build                              # Built in 530ms
  ```
- **Execution Log & Blocker Notes**:
  - Fully verified Python 3.14.7 compatibility.
  - Extracted and integrated `artifacts/intent-check` from developer prototype archive matching the user screenshot.
  - Resolved port conflict on host by making PostgreSQL port configurable via `POSTGRES_PORT` (configured to 5433 in local `.env`).
  - All acceptance criteria satisfied. Blockers: None.

---

#### Task P1-A2: Transaction Domain Models & State Machine
- **Owner / Agent**: Senior Software Architect / Backend Engineer (Agent 2)
- **Status**: `DONE`
- **Objective**: Implement the transaction domain entity, auditable 10-state workflow finite state machine (`INITIATED`, `ASSESSING`, `RISK_ASSESSED`, `DECISION_READY`, `VERIFICATION_REQUIRED`, `HELD_FOR_VERIFICATION`, `INVESTIGATING`, `HUMAN_REVIEW`, `SETTLED_SIMULATED`, `CANCELLED_SIMULATED`), transition validation rules, SQLAlchemy transaction and audit models, Alembic migration, repository persistence with customer-scoped idempotency and optimistic locking, transaction application service, API request/response schemas, and thin endpoints at `/api/v1/transactions` with unit, database integration, and API tests.
- **Dependencies**: Task P1-A1 completion.
- **Acceptance Criteria**:
  - [x] 10-state transaction lifecycle defined and enforced with domain policy.
  - [x] Decimal-safe monetary arithmetic, customer ID, idempotency key, currency, rail, recipient details.
  - [x] Append-only transaction state transition audit model (`transaction_audits`).
  - [x] SQLAlchemy 2.x async models with indices, unique constraints, and optimistic versioning.
  - [x] Versioned Alembic migration `0002_create_transactions_and_audits.py` created and applied.
  - [x] Repository with customer-scoped idempotency and payload conflict detection.
  - [x] Thin FastAPI endpoints: create, retrieve, bounded list, transition, audit history.
  - [x] Comprehensive unit tests (transitions, invariants, terminal states).
  - [x] Database integration tests with isolated PostgreSQL transactions.
  - [x] API tests covering 201/200 idempotent replay, 404, 409 conflict, and 400 invalid transitions.
  - [x] All linting (Ruff), type checking (mypy), and test suites pass.
  - [x] Existing frontend builds and passes all tests.
- **Verification Commands & Results**:
  ```bash
  cd backend
  uv run alembic upgrade head                # Applied 0002_transactions
  uv run pytest                              # 63 passed in 0.99s
  uv run ruff check .                        # All checks passed!
  uv run ruff format --check .               # 33 files already formatted
  uv run mypy app                            # Success: no issues found in 22 source files
  make check-all                             # All backend and frontend checks passed
  ```
- **Execution Log & Blocker Notes**:
  - Authoritative 10-state lifecycle implemented in `app.domain.state_machine` with `validate_transition()`, `can_transition()`, and `is_terminal()`.
  - Concurrency protected via `(customer_id, idempotency_key)` uniqueness and integer optimistic version locking.
  - Created isolated PostgreSQL `test_aegispay` database for integration tests.
  - All 63 backend tests passed; all frontend unit tests (7 passed) and production build passed without regression. Blockers: None.

---

#### Task P1-A3: Deterministic Risk Engine & Scenario-Driven Assessment
- **Owner / Agent**: Senior Software Architect / Backend Engineer (Agent 3)
- **Status**: `DONE`
- **Objective**: Implement an explainable, deterministic transaction risk engine and integrate it with the existing transaction backend and frontend. Evaluates actual transaction and evidence inputs without ML/LLM dependencies or scenario branching. Differentiates risk levels (LOW, MEDIUM, HIGH, CRITICAL) and recommends policy actions (ALLOW, WARN_CUSTOMER, REQUIRE_VERIFICATION, HOLD_FOR_INVESTIGATION) while explicitly recording missing evidence and preserving state machine lifecycle transitions and audit trails.
- **Dependencies**: Tasks P1-A1 and P1-A2 completion.
- **Acceptance Criteria**:
  - [x] Deterministic feature evaluation: amount/history, first-time vs established recipient, recipient fan-in/fan-out and risk flags, recent financial activity (FD liquidation), behavioral signals (active call, screen sharing), structured context (coercion cues, guaranteed returns, invoice mismatch).
  - [x] Missing evidence explicitly identified and retained as unknown, not silently assumed safe or suspicious.
  - [x] Explainable assessment schema: relative risk score (0-100), risk level, triggered rules with weights/evidence, missing evidence list, recommended action, concise explanation.
  - [x] No scenario IDs, hardcoded scenario scores, or keyword-to-score shortcuts in the engine.
  - [x] State machine integration: transitions from `INITIATED` through `ASSESSING` to `RISK_ASSESSED` and `DECISION_READY` with atomic audit logging.
  - [x] Policy rules enforced: trusted recipient cannot override coercion; voice stress alone is not proof of fraud; all holds/cancellations explicitly simulated.
  - [x] All six demo scenarios evaluated purely on their supplied feature inputs with explainable outcomes.
  - [x] API endpoints exposed and documented: `/api/v1/transactions/{id}/assess` and `/api/v1/risk/evaluate`.
  - [x] Persistence of assessments with Alembic migration (`0003_create_transaction_assessments.py`).
  - [x] React frontend connected to backend assessment endpoints, displaying score, level, evidence, rules, missing fields, and actions in the console and simulator.
  - [x] Full unit and integration test suite covering rules, boundaries, missing evidence, all 6 scenarios, and concurrency.
  - [x] Quality gates (Ruff, mypy, pytest, ESLint, tsc, Vitest, make check-all) pass with zero errors.
- **Verification Commands & Results**:
  ```bash
  cd backend
  uv run alembic upgrade head                # Applied 0003_transaction_assessments
  uv run pytest                              # 78 passed in 1.29s
  uv run ruff check .                        # All checks passed!
  uv run ruff format --check .               # 41 files already formatted
  uv run mypy app                            # Success: no issues found in 28 source files
  cd ../frontend
  npm run lint                               # 0 errors, 0 warnings
  npm run typecheck                          # 0 errors
  npm test                                   # 9 passed in 2 test files
  npm run build                              # Built in 560ms
  make check-all                             # 100% passed across both services
  ```
- **Execution Log & Blocker Notes**:
  - Implemented `RiskEngine` with 11 explainable deterministic rules covering high-value anomaly, elevated amount monitoring, new payee, sudden term deposit liquidation, telephony telemetry (active call + screen share), authority duress / coercion, guaranteed returns investment scheme, coaching to bypass bank warnings, vendor ledger / routing mismatch, consortium mule account hit, mule fan-in / fan-out velocity, vocal stress advisory, and trusted recipient mitigation.
  - Preserved critical policy guardrails: trusted-recipient mitigation is strictly bypassed when active coercion is detected; voice stress alone has a low weight (+5) and cannot block transactions; missing telemetry signals are explicitly surfaced in `missing_evidence` without safe/suspicious assumptions.
  - Built `TransactionAssessmentModel` with JSON columns and linked to `TransactionModel`. Applied Alembic migration `0003_create_transaction_assessments.py`.
  - Created `RiskService` orchestrating the atomic transition flow (`INITIATED` -> `ASSESSING` -> `RISK_ASSESSED` -> `DECISION_READY`) with audit logging.
  - Exposed `POST /api/v1/risk/evaluate`, `GET /api/v1/risk/scenarios`, `POST /api/v1/transactions/{id}/assess`, and `GET /api/v1/transactions/{id}/assessment`.
  - Built frontend `riskApi.ts` client with concrete fixtures for all 6 demo fraud scenarios (`digital_arrest`, `investment_scam`, `fake_invoice`, `mule_network`, `legitimate_high_value`, `ambiguous_payment`).
  - Added dedicated "Risk assessment" drawer tab displaying relative risk score (0-100), severity level pill, recommended action, triggered rules with weights/evidence, supporting findings, and missing telemetry warnings.
  - Added Risk score column to the bank-wide payment activity table.
  - Total tests: 78 backend tests + 9 frontend tests (87 tests total, 100% passing). Blockers: None. Phase 1 complete.

---

#### Task P1-A4: Risk Engine Verification and Demo Readiness
- **Owner / Agent**: Senior Software Architect / Full-Stack Engineer (Agent 4)
- **Status**: `DONE`
- **Objective**: Verify the completed P1-A1 through P1-A3 implementation, fix confirmed issues, test boundaries, verify offline fallback clarity, ensure clean database migration parity, and establish reliable end-to-end demo readiness before starting Phase 2.
- **Dependencies**: Tasks P1-A1, P1-A2, and P1-A3 completion.
- **Acceptance Criteria**:
  - [x] All six scenario fixtures executed and verified against the actual deterministic risk engine with explainable scores, rules, missing signals, and recommendations.
  - [x] Verified active-call alone and voice-stress alone do not establish fraud or cause blocks (covered in unit tests).
  - [x] Verified trusted recipients do not override strong coercion indicators (coercion bypass guardrail).
  - [x] Verified ambiguous evidence remains ambiguous without auto-blocking (requires verification, records missing fields).
  - [x] Backend and frontend behavior verified when API is unavailable; clearly distinguished live backend assessments (`Live Backend Assessment` green badge) from demo fallback results (`Demo Fallback (Offline Mode)` amber badge and informative banner).
  - [x] Tested assessment persistence, repeated requests (rejected on DECISION_READY transactions), concurrent transitions (optimistic locking 409), complete valid lifecycle transitions, and atomic audit records.
  - [x] Verified endpoint authorization and validation boundaries; confirmed real banking action names (`SETTLED`, `CANCELLED`) are rejected and only `_SIMULATED` terminal states are accepted.
  - [x] Confirmed migrations run cleanly from a blank PostgreSQL database from base to head (`0001` -> `0002` -> `0003`) with all relations created.
  - [x] All quality gates (Ruff, mypy, pytest, ESLint, tsc, Vitest, make check-all) pass with 100% success (84 backend tests, 10 frontend tests).
- **Verification Commands & Results**:
  ```bash
  # Clean Database Migration Test
  docker exec -i aegispay_postgres psql -U aegispay_user -d postgres -c "CREATE DATABASE test_clean_aegispay;"
  DATABASE_URL="postgresql+psycopg://aegispay_user:aegispay_dev_pw@127.0.0.1:5433/test_clean_aegispay" cd backend && uv run alembic upgrade head
  # Applied 0001_initial_baseline -> 0002_transactions -> 0003_transaction_assessments

  # Verification Suite
  make check-all
  # Backend:
  # - ruff check: All checks passed!
  # - ruff format: 41 files already formatted
  # - mypy app: Success: no issues found in 28 source files
  # - pytest: 84 passed in 1.68s
  # Frontend:
  # - eslint: 0 errors
  # - tsc: 0 errors
  # - vitest: 10 passed in 2 test files
  # - vite build: built in 576ms
  ```
- **Execution Log & Blocker Notes**:
  - Executed all 6 benchmark fraud scenarios on the pure deterministic engine:
    1. Digital arrest: Score 100, CRITICAL, HOLD_FOR_INVESTIGATION (High-value, new recipient, recent FD liquidation, concurrent call & screen share, authority duress, voice stress advisory).
    2. High-yield investment fraud: Score 65, HIGH, HOLD_FOR_INVESTIGATION (Elevated amount, new recipient, guaranteed return scheme, coached to ignore warnings).
    3. Fake invoice: Score 45, MEDIUM, REQUIRE_VERIFICATION (New recipient, invoice beneficiary identity / routing mismatch).
    4. Mule network: Score 80, CRITICAL, HOLD_FOR_INVESTIGATION (New recipient, consortium mule hit, abnormal fan-in/fan-out velocity).
    5. Legitimate high-value: Score 0, LOW, ALLOW (High-value anomaly mitigated by established trusted beneficiary).
    6. Ambiguous payment: Score 30, MEDIUM, REQUIRE_VERIFICATION (Elevated amount, new recipient, active call; 8 missing fields explicitly preserved as unknown; no automatic block).
  - Explicitly differentiated live backend assessments from demo fallback via `source: 'backend'` vs `source: 'demo_fallback'` in schemas, API client, table pill (`DEMO`), and drawer header badge with fallback banner.
  - Added regression & verification tests for repeated assessments on terminal/decision states, atomic transition lifecycle audits, optimistic concurrency, and simulated action guardrails.
  - Zero Phase 2 AI investigation code introduced. Total tests: 84 backend + 10 frontend (94 tests total, 100% green). Blockers: None.

---

### Phase 2: AI Investigation Agent & Multi-Modal Context Analysis

#### Task P2-A1: Gemini-Powered AI Investigation Service
- **Owner / Agent**: Senior Architect / Full-Stack Engineer (Agent 1)
- **Status**: `DONE`
- **Objective**: Extend the existing FastAPI backend and deterministic risk engine with a Gemini-powered forensic investigation service that analyzes supplied transaction context (transaction details, deterministic risk assessment, customer statements, document extractions, telephony telemetry, recipient intelligence) and returns validated, explainable findings.
- **Deliverables**:
  1. Official Google Gen AI SDK (`google-genai` v2.31.0) async client integration configured for Google Cloud Vertex AI / Gemini Developer API with typed settings (`GEMINI_MODEL_ID`, `GCP_PROJECT_ID`, `GCP_LOCATION`, `GEMINI_API_KEY`, `GEMINI_REQUEST_TIMEOUT_SECONDS`, `GEMINI_MAX_RETRIES`).
  2. Domain value types (`FindingCategory`, `RiskSentiment`, `ConfidenceLevel`, `EvidenceProvenance`, `InvestigationFinding`, `InvestigationModelMetadata`, `InvestigationResult`).
  3. Structured Pydantic v2 schemas: request models (`CustomerStatementEvidence`, `DocumentExtractionEvidence`, `TelephonyTelemetryEvidence`, `RecipientIntelligenceEvidence`, `InvestigateTransactionRequest`), Gemini JSON generation schema (`InvestigationFindingSchema`, `InvestigationStructuredOutput`), and response models (`InvestigationFindingResponse`, `InvestigationModelMetadataResponse`, `InvestigationResponse`, `InvestigationListResponse`).
  4. System prompts with strict anti-prompt-injection boundaries (`<untrusted_customer_statements>`, `<untrusted_extracted_documents>`, `<untrusted_context_cues>`), instruction ignoring rules, and core operational guardrails (voice stress alone does not establish fraud; trusted beneficiary does not negate duress; AI produces forensic intelligence and never mutates transaction states).
  5. SQLAlchemy model `TransactionInvestigationModel` with JSON columns and foreign keys (`transactions.id`, `transaction_assessments.id` with `ondelete="SET NULL"`).
  6. Alembic async migration `0004_create_transaction_investigations` applied to PostgreSQL.
  7. Transaction repository methods: `create_investigation`, `get_investigation_by_id`, `list_investigations_for_transaction`.
  8. AI client architecture: `AIInvestigationClient` protocol, `VertexGeminiClient` (async `generate_content`, exponential backoff retry on 5xx, timeout handling, error mapping), and `MockGeminiClient` (offline contextual scenario synthesis and simulated failure modes).
  9. Application service `InvestigationService` orchestrating transaction validation, context collation, Gemini generation, and persistence without mutating transaction state or version.
  10. REST API endpoints: `POST /api/v1/investigations`, `GET /api/v1/investigations/{id}`, `GET /api/v1/transactions/{id}/investigations`.
  11. Frontend typed API client (`frontend/src/api/investigationApi.ts`) with complete TypeScript interfaces and fetch helpers.
  12. Unit tests (`backend/tests/unit/test_investigation_service.py`) and integration tests (`backend/tests/integration/test_investigations_api.py`) verifying prompt construction, anti-prompt injection, schema parsing, error mapping, database persistence, and transaction state non-mutation invariants.
- **Acceptance Criteria**:
  - [x] Official `google-genai` SDK integrated without third-party agent frameworks (no LangChain/LangGraph).
  - [x] Structured JSON output parsed and strictly validated using Pydantic v2 schemas.
  - [x] Provider selection configured via `AI_PROVIDER` (`auto`, `vertex_ai`, `gemini_api`, `mock`), explicitly declaring `"mock_gemini"` vs `"vertex_ai"` in `model_metadata.provider`.
  - [x] Evidence integrity enforced: all citations validated against supplied input allowlist; fabricated references scrubbed and recorded in `missing_information`.
  - [x] Provenance allowlist enforced with `model_inference` fallback for ungrounded claims.
  - [x] Prompt injection resistance verified: adversarial overrides inside customer statements are fenced and flagged as `SOCIAL_ENGINEERING`; neutralized away from `MALICIOUS` customer sentiment.
  - [x] Input payload bounds enforced (`customer_statements` max 50, `document_extractions` max 20, `coercion_cues` max 20).
  - [x] Upstream errors cleanly mapped: timeout -> HTTP 504 (`AI_PROVIDER_TIMEOUT`), rate limit -> HTTP 429 (`AI_RATE_LIMIT_EXCEEDED`), permission denied (403) -> HTTP 502 (`AI_PERMISSION_DENIED`), provider error -> HTTP 502 (`AI_PROVIDER_ERROR`), missing configuration -> HTTP 503 (`AI_CONFIGURATION_ERROR`).
  - [x] State-machine invariant strictly enforced: transaction state, version, and audit trail are immutable during investigation creation, retrieval, or upstream failure.
  - [x] Clean database migration verified: base to head (`0001` -> `0002` -> `0003` -> `0004`) on clean PostgreSQL database.
  - [x] Endpoints exposed: `POST /api/v1/investigations`, `GET /api/v1/investigations/{id}`, `GET /api/v1/transactions/{id}/investigations`.
  - [x] All 111 backend tests and 10 frontend tests pass (121 tests total, 100% green).
  - [x] Backend and frontend linting, formatting, and type checks pass with zero warnings or errors.
- **Verification Commands & Results**:
  ```bash
  # Alembic clean database migration verification
  DATABASE_URL="postgresql+psycopg://aegispay_user:aegispay_dev_pw@localhost:5433/alembic_clean_test" uv run alembic upgrade head
  # Applied: 0001_initial_baseline -> 0002_transactions -> 0003_transaction_assessments -> 0004_transaction_investigations

  # Full verification suite
  make check-all
  # Backend:
  # - ruff check .: All checks passed!
  # - ruff format --check .: 50 files already formatted
  # - mypy app: Success: no issues found in 35 source files
  # - pytest: 111 passed in 2.61s (19 unit investigation tests, 8 integration tests)
  # Frontend:
  # - eslint .: 0 errors, 0 warnings
  # - tsc --noEmit: 0 errors
  # - vitest run: 10 passed in 2 test files
  # - vite build: built in 555ms
  ```
- **Execution Log, Security & Blocker Notes**:
  - **Live Gemini Provider Smoke Test**: `UNVERIFIED (NO_CREDENTIALS)`. Neither `GCP_PROJECT_ID` nor `GEMINI_API_KEY` is provisioned in the local environment. When `AI_PROVIDER=auto`, the application explicitly fails with HTTP 503 `AI_CONFIGURATION_ERROR` rather than masquerading mock data as live AI output.
  - **Authorization & Access Control**: Documented as an **architectural blocker / known limitation** for multi-tenant production. Endpoints currently lack authentication (JWT/session) and object-level authorization (IDOR/BOLA protections). Any client with a valid transaction or investigation UUID can request or read investigation records. Must be addressed before multi-user deployment.
  - **Evidence Integrity Verification**: `InvestigationService._validate_and_sanitize_evidence_integrity` validates all model findings against supplied input tokens (`stmt_*`, `doc_*`, telemetry sensors, registry flags, triggered rules). Hallucinated references (e.g. `stmt_999`, unsupplied registries) are stripped and logged in `missing_information`. Findings with empty evidence citations default to `EvidenceProvenance.MODEL_INFERENCE`.
  - **Adversarial Non-Malice Invariant**: Untrusted customer statements attempting prompt injection (e.g. `SYSTEM OVERRIDE`) are flagged under `SOCIAL_ENGINEERING` but cannot classify the customer as `MALICIOUS`. Malicious classification is strictly reserved for confirmed mule/beneficiary fraud.
  - Zero Phase 2 Task P2-A2 code initiated. All verification criteria satisfied.

#### Task P2-A2: Bounded Multi-Turn Investigation Conversation
- **Owner / Agent**: Senior Architect / Full-Stack Engineer (Agent 1)
- **Status**: `DONE`
- **Objective**: Implement a bounded, multi-turn AI investigation conversation on top of the existing P2-A1 AI investigation capability. Enable operators to supply customer-provided messages, call transcripts, or notes, receive evidence-grounded forensic findings, answer targeted follow-up questions, and refine the investigation context iteratively without mutating transaction state or audit records.
- **Deliverables**:
  1. Configuration setting `INVESTIGATION_MAX_CONVERSATION_TURNS: int = 20` in `backend/app/core/config.py` and `.env.example`.
  2. Domain models in `backend/app/domain/investigation.py`: `ConversationRole` (`operator`, `assistant`, `system`), `ConversationStatus` (`ACTIVE`, `COMPLETED`, `CLOSED`), `ConversationTurn`, and `EvidenceProvenance.AI_ASSISTANT`.
  3. Prompt engineering in `backend/app/domain/investigation_prompts.py`: `CONVERSATION_INVESTIGATION_SYSTEM_INSTRUCTION` and `build_conversation_investigation_prompt` with chronological history collation, untrusted boundary fences, and grounding instructions.
  4. Pydantic schemas in `backend/app/schemas/investigation.py`: `StartConversationRequest`, `AddConversationTurnRequest`, `ConversationTurnStructuredOutput`, `ConversationTurnResponse`, `InvestigationConversationResponse`, and `InvestigationConversationListResponse`.
  5. Error definitions in `backend/app/core/errors.py`: `ConversationTurnLimitError` (HTTP 400, `CONVERSATION_TURN_LIMIT_EXCEEDED`) and `ConversationInactiveError` (HTTP 400, `CONVERSATION_INACTIVE`).
  6. SQLAlchemy models in `backend/app/db/models.py`: `InvestigationConversationModel` and `InvestigationConversationTurnModel` with foreign keys, cascading turns, optimistic locking, and relationships.
  7. Alembic migration `backend/app/db/migrations/versions/0005_create_investigation_conversations.py` applied cleanly to PostgreSQL.
  8. Repository methods in `backend/app/repositories/transaction_repository.py`: `create_conversation`, `get_conversation_by_id`, `get_active_conversation_for_transaction`, `list_conversations_for_transaction`, `create_conversation_turn`, `update_conversation`, and eager-loaded relationship management.
  9. AI client protocol extension in `backend/app/services/ai_client.py`: `generate_conversation_turn` implemented on `AIInvestigationClient`, `VertexGeminiClient`, and `MockGeminiClient` with non-repeating follow-up question synthesis and evidence reference extraction.
  10. Application service in `backend/app/services/investigation_service.py`: `start_or_get_conversation`, `get_conversation`, `list_conversations_for_transaction`, `submit_conversation_turn`, and `_validate_and_sanitize_turn_integrity` with strict non-mutation of transaction records.
  11. REST API endpoints in `backend/app/api/conversations.py` and `backend/app/api/transactions.py`:
      - `POST /api/v1/transactions/{id}/conversations`: start or retrieve active conversation.
      - `GET /api/v1/transactions/{id}/conversations/current`: fetch active conversation.
      - `GET /api/v1/transactions/{id}/conversations`: list all conversations for transaction.
      - `POST /api/v1/transactions/{id}/conversations/{conv_id}/turns`: submit operator turn (scoped to transaction).
      - `GET /api/v1/conversations/{id}`: fetch conversation by ID.
      - `POST /api/v1/conversations/{id}/turns`: submit turn by conversation ID.
  12. Frontend API client in `frontend/src/api/investigationApi.ts`: `startInvestigationConversationApi`, `getCurrentConversationForTransactionApi`, and `submitConversationTurnApi` with typed interfaces.
  13. Interactive React component `frontend/src/components/InvestigationConversationPanel.tsx` mounted inside `TransactionDrawer` in `frontend/src/App.tsx` under `'AI Investigation'` tab with turn counter, AI provider badge, risk sentiment, forensic findings, clickable follow-up inquiry chips, input composer, provenance selector, and non-mutation advisory notice.
  14. Comprehensive test suites:
      - Unit tests in `backend/tests/unit/test_investigation_service.py` (24 tests).
      - Integration tests in `backend/tests/integration/test_investigations_api.py` (10 tests).
      - Frontend unit and integration tests in `frontend/src/__tests__/InvestigationConversationPanel.test.tsx` (4 tests).
- **Acceptance Criteria**:
  - [x] Multi-turn conversation capability bounded to 20 turns (`INVESTIGATION_MAX_CONVERSATION_TURNS`).
  - [x] State-machine invariant preserved: transaction state, version, and audit records remain 100% immutable throughout all conversation turns.
  - [x] Strict cross-transaction isolation: verified that accessing or submitting turns across mismatched transactions fails with HTTP 404 (`RESOURCE_NOT_FOUND`).
  - [x] Client-provided turn idempotency supported via `client_turn_id`.
  - [x] Evidence integrity validated: findings grounded in conversation statements or prior turns.
  - [x] Provider transparency: model metadata explicitly declares `"mock_gemini"` vs `"vertex_ai"`.
  - [x] Follow-up questions generated contextually without repeating inquiries already answered in history.
  - [x] Database migration applied cleanly (`0005_create_investigation_conversations`).
  - [x] All 118 backend tests and 14 frontend tests pass (132 total tests, 100% green).
  - [x] Backend and frontend linting, formatting, and type checks pass with zero warnings or errors.
- **Verification Commands & Results**:
  ```bash
  # Full repository check
  PATH=$HOME/.local/bin:$PATH make check-all
  # Backend:
  # - ruff check .: All checks passed!
  # - ruff format --check .: 52 files already formatted
  # - mypy app: Success: no issues found in 37 source files
  # - pytest: 118 passed in 3.64s
  # Frontend:
  # - eslint .: 0 errors, 0 warnings
  # - tsc --noEmit: 0 errors
  # - vitest run: 14 passed in 3 test files
  # - vite build: built in 558ms
  ```
- **Execution Log, Security & Blocker Notes**:
  - **Primacy of Deterministic Policy**: Verified via `test_conversation_turns_do_not_mutate_transaction_state_or_audit` that initiating conversations and submitting multiple turns preserves transaction `state`, `version`, and audit count (1 from creation).
  - **Authorization & Isolation**: Enforced strict relationship check `conversation.transaction_id == transaction_id` on all transaction-scoped routes. Documented the known architectural lack of JWT/session auth as an ongoing blocker for multi-user deployment.
  - **SQLAlchemy Cache Synchronization**: Required `self.session.expire_all()` after creating conversation turns in repository to ensure eager `selectinload` queries refresh turn collections.
  - Zero Phase 2 Task P2-A3 code initiated. All acceptance criteria satisfied.
- **Post-Implementation Verification Audit (2026-10-17)**: Focused audit of commit `ef3bd10`.
  Two defects found and fixed (committed separately):
  1. `client_turn_id` idempotency was documented/claimed but never enforced — retrying a turn
     with the same token created duplicate operator+assistant turn pairs (reproduced: turn_count
     3 -> 5). Fixed in `investigation_service.submit_conversation_turn` with an idempotent-replay
     check; regression test `test_conversation_turn_client_turn_id_is_idempotent`.
  2. Prompt history fidelity: the service built conversation-history dicts under keys
     (`provenance`, no `turn_index`) that `build_conversation_investigation_prompt` did not read,
     so every prior turn rendered as `index="0" provenance="none"`. Prior-turn **content** was
     always passed correctly; only the index/provenance labels were wrong. Fixed the dict keys;
     regression test `test_conversation_prompt_includes_prior_turns_with_distinct_indices`.
  - Verified: transaction state/version/audit immutability across successful turns, provider
    failures, and rejected requests (AI call precedes all persistence, so provider failure leaves
    no partial writes); DB-level turn-ordering integrity via `uq_conversation_turn_index` (unique
    on `conversation_id, turn_index`, confirmed present in Postgres), which also prevents the
    20-turn bound from being exceeded by concurrent inserts; cross-transaction isolation on
    transaction-scoped routes; untrusted-evidence fencing and prompt-injection non-malice
    neutralization; mock/live provider attribution.
  - **Unresolved security blocker (unchanged)**: endpoints still have NO authentication and NO
    caller-level authorization. The `conversation.transaction_id == transaction_id` relationship
    check is NOT authentication; the `GET/POST /api/v1/conversations/{id}` routes have no scoping
    at all. Any client with a UUID can read or write any conversation. NOT safe for public or
    multi-user deployment; acceptable only for a trusted single-operator private demo.
  - Verification runs: backend `ruff check` clean, `ruff format --check` clean, `mypy app` clean,
    `pytest` 120 passed (118 prior + 2 regression; `test_config::test_default_settings` passes
    only without the local `POSTGRES_PORT=5433` override needed to reach the relocated DB in this
    environment). Frontend: eslint clean, tsc clean, 14 vitest passed, vite build OK.

#### Task P2-A2.1: Authentication & Object-Level Authorization
- **Owner / Agent**: Senior Architect / Full-Stack Engineer
- **Status**: `DONE`
- **Objective**: Add a minimal, real, server-validated authentication and authorization boundary to the operations console, closing the IDOR/no-auth blocker identified in the P2-A2 audit. Built on commit `4746529`. See [ADR-002](../decisions/ADR-002-operator-authentication.md).
- **Decisions (confirmed with user)**: operator-shared authorization; Bearer JWT transport; `operators` table + env bootstrap.
- **Deliverables**:
  1. `pyjwt` + `bcrypt` dependencies; `AUTH_*` settings in `config.py` and `.env.example` (fail-closed: no default `AUTH_JWT_SECRET`).
  2. `app/core/security.py` — bcrypt hashing + HS256 JWT issue/verify (no custom crypto).
  3. `OperatorModel` + migration `0006_create_operators` (unique `username`, bcrypt `password_hash`, `is_active`).
  4. `OperatorRepository`; `app/api/auth.py` with `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, and the `get_current_operator` dependency.
  5. Router wiring: all four console routers (`transactions`, `risk`, `investigations`, `conversations`) gated by `get_current_operator`; `/auth/login` and `/health/*` remain public.
  6. Startup bootstrap (`auth_bootstrap.ensure_bootstrap_operator`, idempotent) provisioning the demo operator from env.
  7. Frontend: `authApi.ts` (token store + `apiFetch` bearer wrapper + 401 forced-logout), all API clients route through `apiFetch`, and an `AuthGate` login screen gating the console (UI otherwise unchanged).
- **Acceptance Criteria**:
  - [x] Identity is server-validated (JWT), never inferred from a caller-supplied id/header.
  - [x] No hardcoded shared password or embedded signing secret; secrets via env; documented bootstrap/login flow.
  - [x] All operations-console routes (incl. the previously unscoped `/conversations/{id}` routes) require authentication; bad credentials/tokens → generic `401 UNAUTHENTICATED`.
  - [x] Established, maintained crypto libraries (`PyJWT`, `bcrypt`); fail-closed when unconfigured.
  - [x] All quality gates pass; new auth tests added.
- **Verification Commands & Results**:
  ```bash
  cd backend
  uv run ruff check .            # All checks passed!
  uv run ruff format --check .   # 60 files already formatted
  uv run mypy app                # Success: no issues found in 43 source files
  uv run pytest                  # 140 passed (+21: 14 auth integration, 7 security unit);
                                 # test_config default-port assertion passes without the local
                                 # POSTGRES_PORT=5433 override used to reach the relocated DB
  # Live smoke (uvicorn): unauth /transactions=401, login=200+JWT, /transactions w/ token=200,
  #   bad password=401, /auth/me=operator identity, /health/live=200 (public). Bootstrap operator
  #   provisioned by lifespan. Server log clean (only expected 401 warnings).
  cd ../frontend
  npm run lint && npm run typecheck   # clean
  npm run test                        # 17 passed (+3 AuthGate)
  npm run build                       # built OK
  ```
- **Execution Log, Security & Blocker Notes**:
  - **Blocker resolved (for the operator model)**: the console is no longer reachable without authentication; the `/conversations/{id}` IDOR surface is gated. The former "no authentication / IDOR" deployment blocker is closed under the operator-shared model.
  - **Remaining future work (not blockers for a private demo)**: per-operator audit attribution, role tiers, token revocation/refresh, `/auth/login` rate limiting, and an external IdP for production multi-tenant use.
  - Zero P2-A3 code initiated.
- **Security Review Hardening (2026-10-17, commit on top of `777fae8`)**: Focused auth
  security review found and fixed two defects:
  1. `decode_access_token` accepted a JWT with no `exp` claim (treated as non-expiring). Now
     `exp` and `sub` are required (`options={"require": [...]}`); a token missing `exp` is
     rejected. Verified alg=none, wrong-key, expired, missing/wrong claims, and HS512-vs-HS256
     algorithm confusion are all rejected.
  2. Login username-enumeration via timing: the unknown-user fallback used a structurally
     invalid dummy hash, so `verify_password` short-circuited (~0 ms) versus a real bcrypt
     verify (~165 ms). Replaced with a real bcrypt hash computed once at import, equalizing
     work across the account-exists and account-missing paths. Response status/code/message
     were already identical.
  Regression tests added (JWT crafted-token suite, dummy-hash structural check, enumeration
  parity, bootstrap-does-not-reset-password, bootstrap-skips-when-config-missing).
  - **Still NOT implemented (material for public production, acceptable for private demo)**:
    no rate limiting / lockout on `/auth/login` (brute-force throttling); HTTPS/TLS is a
    deployment assumption (bearer tokens require transport encryption); `CORS_ORIGINS` and a
    strong `AUTH_JWT_SECRET` must be set per environment. Not public-production ready.

#### Task P2-A3: Operator Investigation Review Panel
- **Owner / Agent**: Senior Architect / Full-Stack Engineer
- **Status**: `DONE`
- **Objective**: Add a polished, read-oriented operator investigation review experience to the
  Aster Bank console so operators can review existing AI investigation results — overview, key
  findings, evidence provenance, and uncertainty/missing information — and move into the existing
  P2-A2 conversation to investigate further. Built on `23d88d4`. **Frontend-only**; reuses P2-A1/
  P2-A2/P2-A2.1 APIs, auth, and styling. No backend change, no migration.
- **Deliverables**:
  1. `frontend/src/components/InvestigationReviewPanel.tsx` — fetches existing investigations via
     the authenticated `fetchInvestigationsForTransactionApi` (routes through `apiFetch`), presents
     the latest investigation, and never auto-launches an investigation.
     - A. Overview: transaction ref, simulated status, deterministic risk score/level (from
       `tx.assessment`, "Not available" when absent), investigation timestamp, AI sentiment,
       AI confidence (qualitative, explicitly **not** a calibrated fraud probability), model/provider.
     - B. Key findings: severity-sorted; category, severity, explanation, evidence refs, and a
       provenance trust classification (independently verified / observed signal / customer-reported
       & unverified / model inference).
     - C. Evidence & provenance index: derived from finding citations; shows each reference, its
       provenance class, and which findings cite it. Clearly states source content is not retained
       in the investigation record (no fabrication) and points to the conversation for live evidence.
     - D. Uncertainty & missing information: dedicated section for missing information, unresolved
       questions, contradictory/mitigating evidence, and suggested next steps.
  2. Integrated into the existing `AI Investigation` drawer tab in `App.tsx`, rendered above the
     reused `InvestigationConversationPanel` (single conversation implementation — not duplicated).
  3. Distinct loading / empty / error / partial-data states; a 404 (unknown/demo transaction) is
     shown as empty, not an error; a manual Refresh re-fetches with an in-flight guard to prevent
     duplicate requests from rapid clicks; latest-first selection avoids stale data.
  4. Frontend tests `frontend/src/__tests__/InvestigationReviewPanel.test.tsx` (12 tests) covering
     the required scenarios (overview, findings, provenance/unverified distinction, evidence index,
     uncertainty visibility, empty, 404-as-empty, partial fields, error, authenticated client use,
     duplicate-click prevention, refresh-after-further-investigation).
- **Security / boundaries**: all requests use the authenticated `apiFetch` client; no protected
  endpoint is called without it; no frontend-only authorization; evidence/model text rendered as
  escaped React text (no `dangerouslySetInnerHTML`); no evidence-integrity checks weakened; no
  transaction state transitions, holds, releases, or AI-triggered actions introduced (read-oriented).
- **Verification Commands & Results**:
  ```bash
  cd frontend
  npm run lint        # clean
  npm run typecheck   # clean
  npm run test        # 29 passed (5 files; +12 new review-panel tests)
  npm run build       # built OK
  cd ../backend       # no backend changes in this milestone
  uv run ruff check . # All checks passed!
  uv run mypy app     # Success: no issues found in 43 source files
  POSTGRES_PORT=5433 uv run pytest  # 148 passed (DB on 5433; test_config default-port
                                    # assertion passes without the override)
  ```
- **Known limitations**:
  - Evidence *content* is not persisted on the investigation record, so the evidence section shows
    the citation/provenance index and directs the operator to the conversation for underlying text
    (deliberate: no new table/migration for presentation, per scope).
  - Seeded demo transactions are not backend records, so the panel shows the empty state for them;
    real backend transactions with a stored investigation render the full review.
  - Recommended next milestone: P2-A3 voice duress agent (still NOT_STARTED) or an authorized human
    decision/adjudication workflow that writes state via the existing state machine.

#### Task P2-A4: Automated Fraud Prevention & Transaction Orchestration
- **Owner / Agent**: Senior Architect / Full-Stack Engineer
- **Status**: `DONE`
- **Objective**: Automated end-to-end decision workflow — evaluate a simulated payment, combine
  deterministic risk with optional investigation evidence, select a permitted action via a
  deterministic policy engine, execute the corresponding simulated state transition, and persist
  an auditable, idempotent decision. Reuses the existing state machine, risk engine, P2-A1
  investigation, P2-A2 conversation, and P2-A2.1 auth. See [ADR-003](../decisions/ADR-003-automated-decision-workflow.md).
- **Deliverables**:
  1. `app/domain/decision_policy.py` — pure deterministic policy engine (`POLICY_VERSION=p2a4.v1`);
     `PolicyAction` enum (ALLOW / REQUIRE_VERIFICATION / HOLD_FOR_INVESTIGATION / BLOCK); typed
     `PolicyInput`/`PolicyDecision`; investigation can only escalate the conservative baseline,
     confidence score never read, BLOCK only on verified consortium mule hit at CRITICAL.
  2. `app/services/decision_workflow_service.py` — orchestration (risk → optional investigation →
     policy → transition → decision persistence); provider-failure fallback; idempotency; optimistic
     concurrency handling.
  3. `TransactionDecisionModel` + Alembic migration `0007_create_transaction_decisions` (verified on
     a clean DB, downgrade/upgrade cycle, and the existing populated DB).
  4. Repository methods `create_decision`, `get_latest_decision_for_transaction`.
  5. Schemas `app/schemas/decision.py` (`EvaluateTransactionRequest`, `WorkflowRiskEvidence`
     reusing the risk evidence fields with amount taken from the transaction, `DecisionResponse`).
  6. Authenticated API on the existing transactions router: `POST /api/v1/transactions/{id}/evaluate`
     (idempotent: 201 on first, 200 on replay) and `GET /api/v1/transactions/{id}/decision`.
  7. Frontend: `frontend/src/api/decisionApi.ts` (evaluate + get-latest via `apiFetch`); decision
     section added to the existing `InvestigationReviewPanel` (action, reason codes, risk, verification
     requirement, from→to state, provider-failure fallback, simulated-outcome labeling, run/replay
     button with duplicate-click guard). No second dashboard.
- **Boundaries**: policy engine never mutates state; LLM never chooses the action; voice-stress-alone
  never a fraud verdict; missing/failed AI never makes high-risk safe; all outcomes are simulated
  states (no real transfer); auth required on both endpoints.
- **Verification Commands & Results**:
  ```bash
  cd backend
  POSTGRES_PORT=5433 uv run alembic upgrade head   # 0006 -> 0007 (clean + existing DB; downgrade ok)
  uv run ruff check .      # All checks passed!
  uv run ruff format --check .   # 66 files already formatted
  uv run mypy app          # Success: no issues found in 47 source files
  POSTGRES_PORT=5433 uv run pytest   # 172 passed (+24: 11 policy unit, 13 workflow/API)
  cd ../frontend
  npm run lint && npm run typecheck  # clean
  npm run test             # 34 passed (+5 decision tests)
  npm run build            # built OK
  # Live uvicorn smoke (AI_PROVIDER=mock): high-risk coercion -> HOLD -> HELD_FOR_VERIFICATION
  #   (simulated); idempotent re-evaluate = 200, stays HELD; low-risk -> ALLOW -> SETTLED_SIMULATED
  #   (investigation skipped); unauthenticated evaluate = 401. Server log clean.
  ```
- **Known limitations**:
  - Decision row and state transition are separate commits; the atomic authoritative record is the
    `transaction_audits` entry (atomicity across the two is NOT claimed — documented in ADR-003).
  - No human adjudication step yet to advance HELD / VERIFICATION_REQUIRED transactions.
  - Workflow runs synchronously (bounded by provider timeout/retries); no async queue.
  - Not public-production ready (inherits P2-A2.1 gaps: `/auth/login` rate limiting, HTTPS/CORS).
  - Recommended next: a human decision/adjudication workflow, or the P2-A3b voice duress agent.

#### Task P2-A5: Automated Verification & Safe Resolution
- **Owner / Agent**: Senior Architect / Full-Stack Engineer
- **Status**: `DONE`
- **Objective**: Implement an automated, secure, simulated customer-verification and transaction-resolution workflow extending P2-A4. Enable simulated transactions in `VERIFICATION_REQUIRED` to issue a challenge, validate simulated OTP submissions securely (keyed HMAC-SHA256 digest, server-side expiry, bounded attempts, single-use consumption under concurrency), and automatically re-evaluate policy to resolve the transaction. Preserves fraud guardrails: verification is an additional signal that never overrides strong fraud evidence. See [ADR-004](../decisions/ADR-004-customer-verification-lifecycle.md).
- **Deliverables**:
  1. `backend/app/core/config.py` & `.env.example`: configuration settings (`VERIFICATION_OTP_LENGTH=6`, `VERIFICATION_CHALLENGE_TTL_SECONDS=300`, `VERIFICATION_MAX_ATTEMPTS=5`, `VERIFICATION_SESSION_TTL_SECONDS=600`, `VERIFICATION_EXPOSE_DEV_OTP=True` for dev/test).
  2. `backend/app/core/security.py`: cryptographically secure OTP generator (`generate_otp`), keyed HMAC-SHA256 digest helpers (`hash_otp`, `verify_otp`), and distinct customer verification session token creation and verification (`create_customer_verification_token`, `decode_customer_verification_token` with `type="customer_verification"`).
  3. `backend/app/core/errors.py`: `VerificationError` with machine-readable error codes (`VERIFICATION_NOT_REQUIRED`, `VERIFICATION_CHALLENGE_INVALID`, `VERIFICATION_EXPIRED`, `VERIFICATION_ALREADY_RESOLVED`).
  4. `backend/app/domain/decision_policy.py`: extended with `VerificationOutcome` (`SUCCEEDED`, `FAILED`, `EXPIRED`, `EXHAUSTED`), `VerificationSignal`, and `_apply_verification` rule. `SUCCEEDED` satisfies `REQUIRE_VERIFICATION` to `ALLOW`, but never downgrades `HOLD_FOR_INVESTIGATION` or `BLOCK` (attaches `VERIFICATION_INSUFFICIENT_RESIDUAL_RISK`). Failed/expired/exhausted outcomes escalate to `HOLD_FOR_INVESTIGATION` and never settle.
  5. `backend/app/db/models.py`: `VerificationChallengeModel` entity with indexed transaction binding, decision foreign key, attempt counts, status, version, and expiry.
  6. Alembic async migration `0008_create_verification_challenges.py`: applied and verified across clean DB, downgrade/re-upgrade, and dev database.
  7. `backend/app/repositories/transaction_repository.py`: challenge methods (`create_challenge`, `get_challenge_by_id`, `get_latest_pending_challenge`, `update_challenge_fields` with optimistic version guard, `set_challenge_decision`).
  8. `backend/app/services/decision_workflow_service.py`: added `resolve_after_verification` to execute valid transitions (`VERIFICATION_REQUIRED` → `INVESTIGATING` → `DECISION_READY`), rebuild policy inputs with verification signal, evaluate `decide()`, apply decision and persist record.
  9. `backend/app/services/verification_service.py`: orchestrates challenge creation, status retrieval, submission verification, single-use consumption, attempt tracking, and policy re-evaluation handoff.
  10. REST API endpoints:
      - `POST /api/v1/transactions/{id}/verification`: operator-authenticated route to create/retrieve active challenge. Returns customer session token and dev OTP (when enabled).
      - `GET /api/v1/transactions/{id}/verification/{challenge_id}`: operator-authenticated challenge status route.
      - `POST /api/v1/verification/{challenge_id}/submit`: customer-session-authenticated route (requires `type="customer_verification"` bearer token) to submit simulated OTP and re-evaluate policy.
  11. Frontend API client `frontend/src/api/verificationApi.ts`: typed helpers for challenge creation, status check, and customer-session submission.
  12. Frontend UI component `frontend/src/components/VerificationPanel.tsx`: integrated into the drawer under the AI Investigation tab. Displays simulated challenge state, dev-mode OTP pill, attempt counter, numeric OTP input with non-digit stripping, and policy re-evaluation outcome with explicit simulated outcome labeling.
  13. Comprehensive test suites:
      - Policy unit tests in `backend/tests/unit/test_decision_policy.py` (16 tests).
      - Verification integration tests in `backend/tests/integration/test_verification_api.py` (15 tests).
      - Frontend unit & integration tests in `frontend/src/__tests__/VerificationPanel.test.tsx` (5 tests).
- **Acceptance Criteria**:
  - [x] Eligible `VERIFICATION_REQUIRED` transaction creates a simulated challenge.
  - [x] Valid OTP submission triggers automated policy re-evaluation.
  - [x] Successful verification with acceptable residual risk permits simulated settlement (`ALLOW`).
  - [x] Successful verification with strong residual fraud evidence remains held (`HOLD_FOR_INVESTIGATION`).
  - [x] Incorrect OTP submission increments attempts and preserves `PENDING` state.
  - [x] Exhausted attempts escalate to `HOLD_FOR_INVESTIGATION` and cannot be retried.
  - [x] Expired challenges reject submissions with `VERIFICATION_EXPIRED`.
  - [x] Consumed challenge cannot be reused; replay returns existing decision idempotently.
  - [x] Token and challenge binding prevents cross-transaction or cross-challenge reuse (HTTP 404).
  - [x] Distinct customer verification session token enforces separation from operator auth.
  - [x] Plaintext OTP is never stored in database (HMAC-SHA256 digest).
  - [x] Optimistic locking on challenge version prevents concurrent double-consumption.
  - [x] Terminal transactions cannot be reopened through verification.
  - [x] All 193 backend tests and 39 frontend tests pass (232 total tests, 100% green).
  - [x] Backend and frontend linting, formatting, and type checks pass with zero warnings or errors.
- **Verification Commands & Results**:
  ```bash
  # Clean database migration verification (upgrade -> downgrade -> re-upgrade)
  POSTGRES_DB=p2a5_clean_test uv run alembic upgrade head
  POSTGRES_DB=p2a5_clean_test uv run alembic downgrade -1
  POSTGRES_DB=p2a5_clean_test uv run alembic upgrade head

  # Full repository verification suite
  make check-all
  # Backend:
  # - ruff check .: All checks passed!
  # - ruff format --check .: 71 files already formatted
  # - mypy app: Success: no issues found in 51 source files
  # - pytest: 193 passed in 13.65s
  # Frontend:
  # - eslint .: 0 errors, 0 warnings
  # - tsc --noEmit: 0 errors
  # - vitest run: 39 passed in 6 test files
  # - vite build: built in 579ms
  ```
- **Execution Log, Security & Blocker Notes**:
  - **Primacy of Deterministic Policy**: Verified that verification success satisfies `REQUIRE_VERIFICATION` but cannot bypass `HOLD_FOR_INVESTIGATION` or `BLOCK` when adverse evidence is present.
  - **Identity Separation**: Operator access tokens (`type="operator_access"`) cannot be used to submit customer verification challenges, and customer verification session tokens (`type="customer_verification"`) cannot access operator console APIs.
  - **Dev-Only Secret Exposure**: Plaintext OTP is exposed strictly via `dev_otp` when `VERIFICATION_EXPOSE_DEV_OTP=True` for simulated prototyping. In production configuration, `dev_otp` is `None`.
  - Zero P2-A3b voice duress code initiated. All acceptance criteria satisfied.

#### Task P2-A5.1: Verification Security & Concurrency Hardening
- **Owner / Agent**: Senior Architect / Full-Stack Engineer
- **Status**: `DONE`
- **Objective**: Remediate findings SEC-01 through SEC-06 identified in the P2-A5 security audit without altering existing business logic or fraud prevention guardrails. Fix ORM session expiration crashes, eliminate the verification-to-decision race condition gap, enforce single pending challenge per transaction via PostgreSQL partial unique index, validate transaction state pre-conditions and handle partial failures, separate HMAC secret keying with dual-key rotation fallback, and bound challenge creation abuse with database-backed window rate limiting.
- **Deliverables**:
  1. `backend/app/core/config.py` & `.env.example`: added `VERIFICATION_HMAC_SECRET: str | None = None`, `VERIFICATION_MAX_CHALLENGES_PER_WINDOW: int = 5`, and `VERIFICATION_CHALLENGE_WINDOW_SECONDS: int = 3600`.
  2. `backend/app/core/security.py`: added `get_verification_hmac_secret`, updated `hash_otp` with explicit secret support, and implemented dual-key verification fallback in `verify_otp` to support seamless zero-downtime key rotation for in-flight challenges.
  3. `backend/app/db/models.py`: declared PostgreSQL partial unique index `uq_verification_challenges_pending_tx` on `verification_challenges(transaction_id)` with `postgresql_where=text("status = 'PENDING'")`.
  4. Alembic migration `0009_enforce_single_pending_challenge.py`: safe forward and rollback migration that deduplicates existing duplicate pending challenges into `SUPERSEDED` status preserving audit records, then creates the partial unique index. Verified on clean DB and existing dev DB.
  5. `backend/app/repositories/transaction_repository.py`:
     - Handled `IntegrityError` in `create_challenge` with explicit rollback and re-raise.
     - Added `count_recent_challenges_for_transaction` to support database-backed creation rate limiting.
     - Removed premature `session.rollback()` in `update_challenge_fields` when `rowcount == 0` to preserve session identity map.
  6. `backend/app/services/verification_service.py`:
     - **SEC-01**: Eliminated `MissingGreenlet` crashes by caching scalar attributes (`cid`, `customer_id`, `version`, `attempt_count`) prior to potential rollbacks or state updates, and re-querying freshly with awaited repository calls.
     - **SEC-02**: Eliminated concurrency race window between `VERIFIED` and `CONSUMED` by introducing bounded in-flight polling (up to 3.0s at 100ms intervals) for both submission and lock contention; added 3-attempt optimistic lock retry loop in `_handle_correct` for racing attempt increments. Never reports success before decision persistence.
     - **SEC-03**: Handled concurrent challenge creation races gracefully by catching `IntegrityError` and returning the winning pending challenge.
     - **SEC-04**: Validated `tx.state == VERIFICATION_REQUIRED` prior to challenge submission, rejecting terminal states (`TRANSACTION_TERMINAL`, 409) and non-required states (`VERIFICATION_NOT_REQUIRED`, 409); implemented partial failure recovery in `_handle_correct` to set `status="FAILED"`, `failure_reason="RESOLUTION_FAILED"` if workflow resolution fails.
     - **SEC-05**: Applied dedicated `VERIFICATION_HMAC_SECRET` with dual-key rotation.
     - **SEC-06**: Enforced database-backed rate limiting (429 `RATE_LIMIT_EXCEEDED`) on challenge creation.
  7. `backend/tests/integration/test_verification_api.py`: Added 7 integration tests covering SEC-01 through SEC-06 (22 tests in file; 200 total backend tests, 100% passing).
  8. Documentation: Updated `docs/decisions/ADR-004-customer-verification-lifecycle.md` and `docs/project/memory.md`.
- **Acceptance Criteria**:
  - [x] Concurrent verification submissions never crash with `MissingGreenlet` (SEC-01).
  - [x] Concurrent correct submissions resolve safely and never claim success before decision persistence (SEC-02).
  - [x] Partial unique index enforces single pending challenge per transaction; concurrent creations resolve cleanly (SEC-03).
  - [x] Submissions on terminal transactions reject with `TRANSACTION_TERMINAL`; partial failures do not strand `VERIFIED` challenges (SEC-04).
  - [x] Dedicated `VERIFICATION_HMAC_SECRET` is decoupled from JWT secret with dual-key rotation support (SEC-05).
  - [x] Challenge creation rate limit bounds repeated creation abuse with HTTP 429 (SEC-06).
  - [x] All 200 backend tests and 39 frontend tests pass (239 total tests, 100% green).
  - [x] Quality gates (`make check-all`: ruff check, ruff format, mypy, pytest, eslint, tsc, vitest, vite build) pass with 0 errors.
- **Verification Commands & Results**:
  ```bash
  # Clean database migration verification (upgrade -> downgrade -1 -> re-upgrade)
  POSTGRES_DB=p2a5_clean_test uv run alembic upgrade head
  POSTGRES_DB=p2a5_clean_test uv run alembic downgrade -1
  POSTGRES_DB=p2a5_clean_test uv run alembic upgrade head

  # Full verification suite
  POSTGRES_PORT=5433 make check-all
  # Backend:
  # - ruff check .: All checks passed!
  # - ruff format --check .: 72 files already formatted
  # - mypy app: Success: no issues found in 52 source files
  # - pytest: 200 passed in 17.32s
  # Frontend:
  # - eslint .: 0 errors, 0 warnings
  # - tsc --noEmit: 0 errors
  # - vitest run: 39 passed in 6 test files
  # - vite build: built in 560ms
  ```
- **Execution Log, Security & Blocker Notes**:
  - All audit findings SEC-01 through SEC-06 resolved.
  - Zero changes to existing fraud guardrails or decision policy semantics.
  - No real payment or SMS rails. Blockers: None.

#### Task P2-A6: Voice Duress Detection & Coercion Intelligence
- **Owner / Agent**: Senior Architect / Full-Stack Engineer
- **Status**: `DONE`
- **Objective**: Extend AegisPay AI with evidence-backed detection of psychological coercion, social-engineering pressure, and simulated voice-derived signals from simulated phone call transcripts. Fully integrate findings into the deterministic decision policy, verification lifecycle, and automated resolution workflow.
- **Deliverables**:
  1. `backend/app/domain/coercion.py`: Domain value types (`CoercionCategory`, `CoercionSeverity`, `CoercionLevel`, `VoiceStressLevel`), dataclasses (`VoiceStressEvidence`, `CoercionFinding`, `CoercionAnalysisResult`), and programmatic verbatim grounding validator `validate_transcript_excerpt()`.
  2. `backend/app/domain/coercion_prompts.py`: Prompt injection-hardened system prompt (`COERCION_ANALYSIS_SYSTEM_INSTRUCTION`) and `build_coercion_prompt()` with untrusted transcript isolation (`<untrusted_simulated_call_transcript>`).
  3. `backend/app/schemas/coercion.py`: Pydantic models for request/response schemas, structured Gemini model output, and simulated voice stress telemetry.
  4. `backend/app/db/models.py`: `TransactionCoercionAnalysisModel` mapped entity linked to `TransactionModel`.
  5. Alembic async migration `0010_create_coercion_analyses.py`: applied and verified across clean DB, downgrade/re-upgrade, and test database.
  6. `backend/app/repositories/transaction_repository.py`: persistence and lookup methods (`create_coercion_analysis`, `get_latest_coercion_analysis`, `get_coercion_analysis_by_id`).
  7. `backend/app/services/ai_client.py`: added `generate_coercion_analysis` to `AIInvestigationClient` protocol, `VertexGeminiClient`, and `MockGeminiClient` (with comprehensive pattern synthesis for authority threats, digital arrest, secrecy, safeguard bypass, urgency, and legitimate explanations).
  8. `backend/app/services/coercion_service.py`: application service managing prompt assembly, AI execution with safe fallback on provider error/timeout (`status="UNAVAILABLE"`), verbatim excerpt validation (discarding hallucinated citations), and transcript deduplication caching.
  9. `backend/app/domain/decision_policy.py`: extended `PolicyInput` with `CoercionSignal`. Policy escalates explicit critical/high coercion to `HOLD_FOR_INVESTIGATION` (`EXPLICIT_COERCION_HOLD`), preserves voice stress advisory boundary (`VOICE_STRESS_ALONE_NON_DISQUALIFYING`), and prevents successful customer OTP verification from clearing strong coercion (`VERIFICATION_INSUFFICIENT_RESIDUAL_RISK`).
  10. `backend/app/services/decision_workflow_service.py`: integrated coercion intelligence into `evaluate` and `resolve_after_verification` automated resolution flows.
  11. REST API in `backend/app/api/coercion.py` & `backend/app/api/router.py`:
      - `POST /api/v1/transactions/{id}/coercion/analyze`: operator-authenticated route to analyze call transcript.
      - `GET /api/v1/transactions/{id}/coercion`: operator-authenticated route to retrieve latest analysis.
  12. Frontend API client `frontend/src/api/coercionApi.ts`: typed fetchers (`analyzeCoercionApi`, `getLatestCoercionApi`).
  13. Frontend UI component `frontend/src/components/CoercionAnalysisPanel.tsx`: integrated into the drawer under the AI Investigation tab. Displays coercion badge, qualitative model certainty notice, voice stress telemetry card with advisory disclaimer, grounded verbatim citations, legitimate explanations, and real-time transcript input with preset templates.
  14. Comprehensive test suites:
      - Domain unit tests in `backend/tests/unit/test_coercion_domain.py` (8 tests).
      - Policy unit tests in `backend/tests/unit/test_decision_policy.py` (21 tests).
      - Coercion API integration tests in `backend/tests/integration/test_coercion_api.py` (14 tests covering all prompt scenarios).
      - Frontend component tests in `frontend/src/__tests__/CoercionAnalysisPanel.test.tsx` (4 tests).
  15. Architectural decision record: `docs/decisions/ADR-005-voice-duress-and-coercion-intelligence.md`.
- **Acceptance Criteria**:
  - [x] Explicit fake-authority threat detected with verbatim transcript citation.
  - [x] Secrecy demands and instructions to bypass bank safeguards detected.
  - [x] Urgency without sufficient coercion evidence does not cause confirmed coercion verdict.
  - [x] Legitimate high-value transfer with plausible explanation recognized and surfaced as mitigating evidence.
  - [x] Ordinary stress without explicit coercion preserves advisory status and does not block/hold.
  - [x] Malformed model output and fabricated citations rejected (grounding invariant).
  - [x] Prompt injection attempts in transcript safely treated as untrusted data under bypass safeguards.
  - [x] Provider timeout/failure applies safe deterministic fallback (`status="UNAVAILABLE"`).
  - [x] Strong coercion evidence remains effective after successful customer verification.
  - [x] Weak voice stress alone never causes a block or fraud verdict.
  - [x] Authorization and transaction scoping enforced (401 unauthenticated, 404 nonexistent tx).
  - [x] Bounded transcript input validation enforced (10 to 10,000 characters).
  - [x] Analysis persistence and auditability verified in database and API.
  - [x] Matching transcript deduplication prevents redundant AI calls.
  - [x] All 227 backend tests and 43 frontend tests pass (270 total tests, 100% green).
  - [x] Full quality gates (`make check-all`: ruff check, ruff format, mypy, pytest, eslint, tsc, vitest, vite build) pass with 0 errors.
- **Verification Commands & Results**:
  ```bash
  POSTGRES_PORT=5433 make check-all
  # Backend:
  # - uv run ruff check .: All checks passed!
  # - uv run ruff format --check .: 80 files already formatted
  # - uv run mypy app: Success: no issues found in 58 source files
  # - uv run pytest: 227 passed in 22.57s
  # Frontend:
  # - eslint .: 0 errors, 0 warnings
  # - tsc --noEmit: 0 errors
  # - vitest run: 43 passed in 7 test files
  # - vite build: built in 588ms
  ```

#### Task P2-A7: Automated Fraud Response & Customer Intervention
- **Owner / Agent**: Senior Architect / Full-Stack Engineer
- **Status**: `DONE`
- **Objective**: Build an end-to-end automated response orchestration layer for AegisPay AI. Consumes transaction risk assessments, deterministic decisions, customer verification outcomes, investigation findings, and coercion intelligence to execute policy-authorized simulated responses and communicate them clearly and empathetically to the customer. All payments, holds, blocks, and notifications remain strictly simulated in sandbox mode.
- **Deliverables**:
  1. `backend/app/domain/response_orchestration.py`: Domain value types (`ResponseType`, `CustomerActionRequired`, `NotificationChannel`, `NotificationDeliveryStatus`, `ResponseProcessingStatus`), `CustomerIntervention` dataclass, mapping table `ACTION_TO_RESPONSE_TYPE`, `build_customer_intervention()` factory for all 4 policy actions, and `mask_recipient_contact()` for phones, emails, and handles.
  2. `backend/app/services/notification_service.py`: `NotificationServiceProtocol` and `SimulatedNotificationService` supporting multiple simulated channels (`IN_APP_SIMULATED`, `SMS_SIMULATED`, `WHATSAPP_SIMULATED`, `EMAIL_SIMULATED`), secret redaction, and `simulate_failure=True` resulting in `FAILED_SIMULATED` with `SIMULATED_CARRIER_TIMEOUT`.
  3. `backend/app/core/errors.py`: Added `FraudResponseError` (HTTP 400) and `StaleDecisionError` (HTTP 409).
  4. `backend/app/db/models.py`: Added `TransactionResponseModel` and `TransactionNotificationModel` mapped entities with back-populates on `TransactionModel`.
  5. Alembic async migration `0011_create_fraud_responses_and_notifications.py`: applied and tested (upgrade head, downgrade -1, re-upgrade head).
  6. `backend/app/repositories/transaction_repository.py`: persistence and query methods (`create_response`, `get_response_by_id`, `get_response_by_decision_id`, `get_latest_response_for_transaction`, `list_responses_for_transaction`, `get_response_by_idempotency_key`, `create_notification`, `get_notifications_for_response`, `get_notification_by_channel`).
  7. `backend/app/schemas/fraud_response.py`: Pydantic request/response schemas (`ExecuteResponseRequest`, `NotificationResponse`, `CustomerInterventionResponse`, `FraudResponseDetails`).
  8. `backend/app/services/response_orchestration_service.py`: `ResponseOrchestrationService` coordinating decision workflow, state verification, intervention generation, notification dispatch, rollback-safe persistence, and customer intervention query.
  9. REST API in `backend/app/api/fraud_responses.py` & `backend/app/api/router.py`:
      - `POST /api/v1/transactions/{id}/respond`: operator-authenticated response orchestration (201 created, 200 replay).
      - `GET /api/v1/transactions/{id}/responses`: operator-authenticated response history.
      - `GET /api/v1/transactions/{id}/responses/latest`: operator-authenticated latest response.
      - `GET /api/v1/transactions/{id}/intervention`: operator or customer-token scoped intervention endpoint.
  10. Frontend API client `frontend/src/api/responseApi.ts`: typed fetchers (`executeResponseApi`, `getLatestResponseApi`, `listResponsesApi`, `getCustomerInterventionApi`).
  11. Frontend UI component `frontend/src/components/CustomerInterventionPanel.tsx`: integrated into `TransactionDrawer` under both `'Decision & history'` and `'AI Investigation'` tabs. Features step progression timeline (Assess → Policy → Response → Alert), response type badge, customer-safe advice card, next steps list, notification delivery card with masked recipient and safety isolation note, operator channel controls with simulated failure toggle, and prominent simulation disclaimer.
  12. Comprehensive test suites:
      - Domain unit tests in `backend/tests/unit/test_response_orchestration_domain.py` (8 tests).
      - Integration tests in `backend/tests/integration/test_response_orchestration_api.py` (11 tests).
      - Frontend component tests in `frontend/src/__tests__/CustomerInterventionPanel.test.tsx` (5 tests).
  13. Architectural decision record: `docs/decisions/ADR-006-automated-fraud-response-and-customer-intervention.md`.
- **Acceptance Criteria**:
  - [x] Authoritative policy decisions automatically execute corresponding simulated response types (`ALLOW_SETTLED`, `VERIFICATION_REQUIRED`, `HOLD_PROTECTIVE`, `BLOCK_SAFETY`).
  - [x] Customer messages are empathetic, non-accusatory, understandable, and free of internal detection jargon or mule keywords.
  - [x] Customer advice warns against calling suspicious phone numbers and directs solely to official bank channels.
  - [x] Notification delivery failure (`FAILED_SIMULATED`) is strictly isolated from safety decisions (cannot downgrade hold or block).
  - [x] Contact identifiers are masked (`***`); zero OTPs, bearer tokens, or transcripts appear in notification bodies or logs.
  - [x] Full idempotency on repeat response requests (`uq_transaction_responses_tx_idempotency`).
  - [x] Concurrency safety with ORM rollback hardening (no `MissingGreenlet` errors).
  - [x] Customer verification tokens are strictly scoped to the transaction ID for intervention access.
  - [x] All 246 backend tests and 48 frontend tests pass (294 total tests, 100% green).
  - [x] All quality gates pass (`make check-all`: ruff check, ruff format, mypy, pytest, eslint, tsc, vitest, vite build).
- **Verification Commands & Results**:
  ```bash
  POSTGRES_PORT=5433 make check-all
  # Backend:
  # - uv run ruff check app/ tests/: All checks passed!
  # - uv run ruff format --check app/ tests/: 87 files already formatted
  # - uv run mypy app: Success: no issues found in 64 source files
  # - uv run pytest: 246 passed in 23.54s
  # Frontend:
  # - eslint .: 0 errors, 0 warnings
  # - tsc --noEmit: 0 errors
  # - vitest run: 48 passed in 8 test files
  # - vite build: built in 600ms
  ```

---

#### Task P2-A8: End-to-End Fraud Simulation & Explainability Dashboard
- **Owner / Agent**: Senior Architect / Full-Stack Engineer
- **Status**: `DONE`
- **Objective**: Let an operator select a predefined fraud scenario, run it through the existing application workflow, inspect the evidence-to-decision-to-intervention timeline, and compare the observed result with the scenario's expected outcome. Simulation/explainability milestone only — no new fraud engine; all payment outcomes remain simulated. See [ADR-007](../decisions/ADR-007-end-to-end-scenario-simulation.md).
- **Deliverables**:
  1. `backend/app/domain/scenario_catalog.py`: versioned (`CATALOG_VERSION=p2a8.v1`) pure-data catalogue of 8 scenarios (digital arrest, investment scam, fake invoice, mule network, legitimate high-value, ambiguous/insufficient-evidence, ordinary stressed customer, strong coercion + successful verification). Each declares simulated inputs, risk/investigation/coercion/voice evidence, verification behaviour, and a separate `ScenarioExpectation` (expected action, final state, response type, customer intervention, verification outcome, limitations). Expectations never feed the pipeline.
  2. `backend/app/domain/scenario_evaluation.py`: pure expected-vs-actual comparison → `MATCH`/`MISMATCH`/`INCOMPLETE` per dimension; preserves the observed outcome; carries an explicit "not real-world accuracy" disclaimer.
  3. `backend/app/services/scenario_orchestration_service.py`: orchestrates the existing `TransactionService`, `RiskService`, `InvestigationService`, `CoercionService`, `DecisionWorkflowService`, `VerificationService`, and `ResponseOrchestrationService`. Deterministic (mock) vs explicit live-provider mode; stage timeline derived from real persisted artifacts; idempotent start + safe retry.
  4. `backend/app/db/models.py` + Alembic migration `0012_create_scenario_runs.py`: `scenario_runs` table (run metadata + ordered JSON `stages` timeline + `transaction_id` FK). Upgrade/downgrade/re-upgrade verified against the dev DB.
  5. `backend/app/repositories/transaction_repository.py`: scenario-run persistence/query methods (create/get/by-idempotency-key/list/update).
  6. `backend/app/schemas/scenario.py`: request/response schemas incl. `ScenarioExecutionMode`.
  7. REST API `backend/app/api/scenarios.py` (operator-authenticated, registered in `router.py`): `GET /scenarios`, `POST /scenarios/{id}/runs`, `GET /scenarios/runs`, `GET /scenarios/runs/{run_id}`, `GET /scenarios/runs/{run_id}/evaluation`, `POST /scenarios/runs/{run_id}/retry`.
  8. Frontend `frontend/src/api/scenarioApi.ts` + `frontend/src/components/ScenarioSimulationPanel.tsx`, mounted as a new `Scenario Lab` surface in `App.tsx` (catalogue, mode toggle, run, timeline with stage states/evidence refs, expected-vs-actual, workflow-success vs decision-correctness distinction, retry, sandbox disclaimer).
  9. Tests: `tests/unit/test_scenario_catalog.py`, `tests/unit/test_scenario_evaluation.py`, `tests/integration/test_scenarios_api.py` (20 tests), and `frontend/src/__tests__/ScenarioSimulationPanel.test.tsx` (3 tests).
- **Acceptance Criteria**:
  - [x] Catalogue has stable ids and versions; 8 required scenarios present.
  - [x] Each scenario executes end-to-end in deterministic mode and its evaluation is `MATCH`.
  - [x] Digital-arrest → `HOLD_FOR_INVESTIGATION` / `HELD_FOR_VERIFICATION`; legitimate high-value → `ALLOW` / `SETTLED_SIMULATED`; ordinary voice stress alone never holds or blocks; successful verification with persistent strong coercion stays held.
  - [x] AI/provider unavailable degrades gracefully (investigation/coercion `UNAVAILABLE`) and the workflow still completes.
  - [x] Expectation never overrides the authoritative observed outcome; evaluation reports `MATCH`/`MISMATCH`/`INCOMPLETE`.
  - [x] No fabricated stage results/timestamps; skipped/unavailable stages explicit.
  - [x] Idempotent runs; concurrent same-key requests create exactly one run; retry reuses the transaction/decision/response without duplicates.
  - [x] Operator authentication enforced on all scenario routes.
  - [x] Migration upgrade/downgrade/re-upgrade verified.
  - [x] All quality gates pass: 276 backend tests, 51 frontend tests, ruff/mypy/eslint/tsc/vite build.
- **Verification Commands & Results**:
  ```bash
  # Backend (POSTGRES_PORT=5433 via .env):
  uv run ruff check .            # All checks passed!
  uv run ruff format --check .   # 97 files already formatted
  uv run mypy app                # Success: no issues found in 70 source files
  uv run pytest                  # 276 passed
  uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head  # OK
  # Frontend:
  npm run lint                   # 0 problems
  npm run typecheck              # 0 errors
  npm run test                   # 51 passed (9 files)
  npm run build                  # built successfully
  ```

---

#### Task P2-A9: Reliability, Security & Demo Readiness
- **Owner / Agent**: Senior Architect / Full-Stack Engineer
- **Status**: `DONE`
- **Objective**: Harden P2-A1..P2-A8 via targeted security review, concurrency/failure testing, migration verification, CI alignment, and a repeatable demo. Reliability milestone only — no new feature/engine/agent. All outcomes remain simulated.
- **Confirmed defects fixed**:
  1. **CI could not run integration tests** — the backend CI job had no PostgreSQL service, so every DB-backed integration test would fail on GitHub Actions. `.github/workflows/ci.yml` now provisions a disposable `postgres:16.8-alpine` service (DB `test_aegispay`, matching creds/env), adds a migration upgrade→downgrade→re-upgrade step, and keeps the frontend job's lint/typecheck/test/build.
- **Hardening added (bounded, testable)**:
  2. **Login throttling** — `app/core/rate_limit.py` `SlidingWindowRateLimiter` + `login_rate_limiter`; `/auth/login` is throttled per **client IP** (never per username, so no account-lockout DoS), returning `429 RATE_LIMIT_EXCEEDED`. Configurable via `AUTH_LOGIN_MAX_ATTEMPTS_PER_WINDOW` (default 10) / `AUTH_LOGIN_WINDOW_SECONDS` (default 60); `0` disables. In-process speed bump (documented limitation: per-process, resets on restart).
  3. **Dev-OTP exposure constrained outside dev/test** — `Settings` `model_validator` forces `VERIFICATION_EXPOSE_DEV_OTP=False` unless `APP_ENV` ∈ {development, dev, local, test, testing, ci}. Fail-safe; cannot leak the simulated OTP in a production-like environment.
- **Verified existing invariants (no code change needed, now regression-covered)**: operator vs customer token types cannot be substituted (distinct `type` claims); a customer token for transaction A cannot access transaction B; AI provider timeout/malformed output never downgrades a risky transaction to ALLOW (deterministic baseline stands); explicit live-provider mode never silently falls back to mock; successful OTP + strong coercion stays held; voice stress alone never holds/blocks; stale decision rejected (`STALE_DECISION`); duplicate response/notification prevented by unique constraints; scenario expectation never overrides the observed outcome; a failed mandatory scenario stage never reports workflow success.
- **New tests**: `tests/unit/test_rate_limit.py` (4), `tests/unit/test_config_security.py` (4), `tests/integration/test_reliability_hardening.py` (9 — login throttle, cross-transaction customer token, operator↔customer token substitution, live-provider missing-credential degradation, scenario partial-failure integrity, duplicate-response single-record, stale decision, observed-outcome authority). Total backend tests: **293**.
- **Demo readiness**: `backend/scripts/smoke_test.py` (stdlib-only; health → login → catalogue → 1 fraud + 1 legitimate scenario; never prints secrets); Makefile `smoke` and `db-verify-migrations` (disposable DB) targets; README "Demo Runbook (Scenario Lab)" with mock-vs-live explanation, walkthrough, dev-OTP instructions, and a troubleshooting table; `.env.example` updated with the login-throttle settings and the dev-OTP constraint note.
- **Verification Commands & Results**:
  ```bash
  make check-all                 # exit 0: backend 293 passed, frontend 51 passed, lint/typecheck/build green
  # Migration integrity on a DISPOSABLE database (dev DB untouched):
  make db-verify-migrations      # upgrade head -> downgrade base -> re-upgrade head, single head 0012, OK
  # End-to-end smoke test against a running server on a disposable DB:
  make smoke                     # all checks PASS (health, login, catalogue, fraud->hold, legit->settled)
  ```
  CI workflow validated to parse and provision the Postgres service + migration step; GitHub Actions result not observed from this environment (reported honestly, not claimed green).
- **Known limitations / unresolved risks**: login throttle is per-process/in-memory (not a distributed edge limiter); no penetration testing performed; no calibrated fraud-detection accuracy or external-provider reliability claimed; HTTPS/TLS, per-environment `CORS_ORIGINS`, and a strong `AUTH_JWT_SECRET` remain deployment responsibilities; not production-ready.

---

#### Task P2-OptA: Dynamic Gemini-Powered Simulated Voice and Chat Dialogue
- **Owner / Agent**: Senior Architect / Full-Stack Engineer (Option A)
- **Status**: `DONE`
- **Objective**: Replace the static, scripted customer-call interactions (`initialQuestions` array and hardcoded regex branches in `App.tsx`) with a dynamic, evidence-driven, multi-turn AI investigation powered by Gemini (`generate_customer_dialogue_turn`). Grounded in transaction facts and evidence, linked to deterministic risk policy, customer verification, and automated resolution. See [ADR-008](../decisions/ADR-008-dynamic-simulated-voice-and-chat.md).
- **Deliverables**:
  1. `backend/app/domain/customer_dialogue.py`: domain entities (`DialogueChannel`, `CallSessionStatus`, `CallSessionDirection`, `CustomerDialogueTurnResult`), anti-prompt-injection prompts (`CUSTOMER_DIALOGUE_SYSTEM_INSTRUCTION`, `build_customer_dialogue_prompt` with `<untrusted_customer_response>` and `<untrusted_dialogue_history>`).
  2. `backend/app/domain/investigation.py`: added `CUSTOMER = "customer"` to `ConversationRole`.
  3. `backend/app/services/ai_client.py`: added `generate_customer_dialogue_turn` to `AIInvestigationClient` protocol, implemented in `VertexGeminiClient` and `MockGeminiClient` (supporting dynamic topic inquiry for authority coercion, high-yield investment scams, supplier invoices, prompt-injection defense, and terminal hold recommendations).
  4. `backend/app/db/models.py` & Alembic migration `0013_create_customer_call_sessions.py`: `transaction_call_sessions` table with optimistic locking and `conversation_type` on `investigation_conversations`.
  5. `backend/app/repositories/transaction_repository.py`: call session repository methods with eager relationship loading (`selectinload`) and scalar caching before commit to prevent SQLAlchemy `MissingGreenlet` errors.
  6. `backend/app/services/customer_dialogue_service.py`: orchestrates call session lifecycle (`initiate`, `connect`, `submit_turn`, `complete`, `decline`), bounds turns, and automatically invokes `CoercionService.analyze_transaction_coercion` on session completion.
  7. `backend/app/api/customer_dialogue.py`: REST routes mounted under `/api/v1/transactions/{id}/calls` and `/api/v1/calls/{id}/*` authenticated via operator JWT or customer verification token.
  8. `frontend/src/api/customerDialogueApi.ts`: typed API client bindings for call sessions.
  9. `frontend/src/App.tsx`: wired backend transaction creation, call session initiation, dynamic speech/chat turns with Web Speech API and text fallback, intelligent scenario-aware demo responses, and drawer panel transaction ID synchronization.
  10. Tests:
      - Backend: `tests/unit/test_customer_dialogue_domain.py` (6 tests), `tests/integration/test_customer_dialogue_api.py` (11 tests). Total 310 backend tests passing.
      - Frontend: `frontend/src/__tests__/CustomerDialogue.test.tsx` (6 tests). Total 57 frontend tests passing.
- **Acceptance Criteria**:
  - [x] Replaced static scripted 3-question sequence with dynamic Gemini-powered multi-turn dialogue.
  - [x] Deterministic risk policy remains authoritative; Gemini turns provide structured forensic observations and conversational questions.
  - [x] Prompt injection defense enforced (`<untrusted_customer_response>`).
  - [x] Voice stress remains purely advisory (`VOICE_STRESS_ALONE_NON_DISQUALIFYING`).
  - [x] Call sessions persist in database with optimistic locking and linked conversation turns.
  - [x] Coercion analysis automatically triggers upon call session completion.
  - [x] Authenticated routes support both operator JWT and customer verification tokens.
  - [x] Web Speech recognition and audio synthesis with text chat fallback work seamlessly in mobile phone simulator.
  - [x] All 310 backend tests and 57 frontend tests pass (100% green).
- **Verification Commands & Results**:
  ```bash
  # Backend
  POSTGRES_PORT=5433 uv run pytest              # 310 passed in 34.39s
  uv run ruff check .                           # All checks passed!
  uv run ruff format --check .                  # 102 files already formatted
  uv run mypy app                               # Success: no issues found in 75 source files
  # Frontend
  npm run test                                  # 57 passed (10 test files)
  npm run build                                 # built successfully
  ```

---

#### Task P2-A10: Customer Dialogue Reliability Audit & Fixes
- **Owner / Agent**: Reliability Audit (Option A hardening)
- **Status**: `DONE`
- **Objective**: Audit the staged P2-OptA customer-dialogue implementation for correctness, concurrency, lifecycle, security, and integration defects before commit, and fix confirmed issues with regression tests.
- **Confirmed defects fixed**:
  1. **Lifecycle (A1)** — `complete_call_session` overwrote terminal states (`DECLINED`/`TIMED_OUT`/`FAILED`/`CANCELLED` → `COMPLETED`), corrupting the audit trail. Now rejects non-`COMPLETED` terminal states with `ConflictError`; idempotent on `COMPLETED`.
  2. **Lifecycle (A2)** — a failed initial Gemini generation left a persisted active (`RINGING`) session with no turns, which the active-session guard then kept returning. Initiation now persists the session first, and on AI failure marks it `FAILED` (terminal) and closes the conversation, so retries start fresh.
  3. **Concurrency (B1)** — no DB constraint enforced "one active session per transaction"; the read-before-write guard alone could not stop concurrent duplicates. Added partial unique index `uq_call_sessions_active_tx` (model + migration `0013`); initiation resolves the `IntegrityError` by returning the winning session.
  4. **Concurrency (B2)** — a racing turn at a taken `(conversation_id, turn_index)` surfaced as an unhandled 500. `create_conversation_turn`/`create_call_session` now roll back and re-raise on `IntegrityError`; `submit_turn` maps it to a 409 `ConflictError`.
  5. **Coercion policy (C1)** — automatic completion triggered coercion analysis from only the final assistant turn. It now evaluates accumulated evidence across all turns.
  6. **Coercion policy (C2)** — manual `complete` did not run coercion analysis (inconsistent with automatic completion). A shared `_maybe_link_coercion_analysis` helper now runs on both paths; AI/coercion failures remain logged-and-swallowed and never corrupt the lifecycle or transaction state.
  7. **Security (D1)** — internal forensic fields (internal observations, uncertainty notes, suggested action, coercion cues, risk sentiment, evidence references) were returned to customer sessions. `_to_call_session_response` now redacts them for non-operators.
  8. **Security (D2)** — customer verification tokens (bound to one transaction) could access any transaction's call session (IDOR). `authorize_call_access` now returns the bound `transaction_id` and every route enforces the customer scope; added `AuthorizationError` (HTTP 403).
  9. **Frontend (F1)** — turn submissions were not idempotent and had no in-flight guard. `App.tsx` now sends a per-answer `client_turn_id` and blocks re-entrant submissions.
- **Regression tests added** (8 backend in `tests/integration/test_customer_dialogue_api.py`, 1 frontend in `CustomerDialogue.test.tsx`): terminal-state completion rejection, AI-failure-then-retry, active-session unique constraint, duplicate-turn 409, coercion-before-final-turn + manual completion, idempotent turn replay, cross-transaction authorization (403), customer field redaction, and idempotent `client_turn_id`.
- **Not changed (verified already safe)**: `(conversation_id, turn_index)` uniqueness already existed; coercion grounding/voice-stress-advisory invariants and deterministic policy authority already upheld.
- **Known limitations**: `TIMED_OUT` remains a reserved status with no server-side timeout sweeper (the dialogue is bounded by `MAX_DIALOGUE_TURNS` and client-driven decline/complete). True concurrent-load behavior was not stress-tested; `IntegrityError` paths are covered by DB-constraint tests, not live races.
- **Verification Commands & Results**:
  ```bash
  POSTGRES_PORT=5433 uv run pytest              # 318 passed in ~35s
  uv run ruff check .                           # All checks passed!
  uv run ruff format --check .                  # 109 files already formatted
  uv run mypy app                               # Success: no issues found in 76 source files
  POSTGRES_PORT=5433 make db-verify-migrations  # upgrade/downgrade/re-upgrade OK (incl. 0013 partial index)
  npm run lint / typecheck / test / build       # 58 frontend tests passed; build OK
  POSTGRES_PORT=5433 make check-all             # full gate green
  ```

---

#### Task P2-A11: Real-Time Gemini Live Voice Agent & Streaming Fraud Intelligence
- **Owner / Agent**: Full-Stack Engineer (real-time voice)
- **Status**: `DONE` (provider integration verified with mocks only — see limitations)
- **Objective**: Upgrade the simulated voice path to true real-time bidirectional audio via the
  Gemini Live API, streaming audio both ways over an authenticated WebSocket, persisting the
  transcript incrementally, and running evidence analysis in parallel while the call is live.
  Deterministic fraud policy remains the sole authority for transaction-state changes.
- **Deliverables**:
  1. `backend/app/core/config.py`: `GEMINI_LIVE_*` settings (flag, model, voice, bounded session
     seconds, sample rates, frame/queue caps, concurrency cap, analysis cadence) + a validator that
     fails clearly if Live is enabled without credentials.
  2. `backend/app/domain/live_voice.py`: transcript speaker/kind enums, `LiveAnalysisStatus`, the
     versioned `LiveEvidenceSnapshot`/`LiveEvidenceFinding` contract (`live-analysis-v1`), and the
     natural conversational agent system instruction (dynamic, non-accusatory, no scripts, no raw
     scores, voice-stress-not-proof).
  3. `backend/app/services/live_voice_client.py`: provider-agnostic `LiveVoiceClient`/`LiveVoiceSession`
     interface, a real `GeminiLiveVoiceClient` over `google-genai` 2.31.0 (`aio.live.connect`, audio
     in/out transcription, speech voice, session resumption, context-window compression), and a
     deterministic `MockLiveVoiceClient` for tests/offline.
  4. `backend/app/services/live_voice_analysis.py`: grounded incremental `LiveEvidenceAnalyzer`
     producing the versioned snapshot with transcript-span references (offline-deterministic; a
     Gemini text strategy can be swapped in).
  5. `backend/app/services/live_voice_service.py`: `LiveVoiceOrchestrator` — bounded queues, independent
     ingest/egress/persistence/analysis/watchdog tasks, single-writer monotonic `seq`, dedup, barge-in,
     resumption handle capture, deterministic cancellation/cleanup, and finalize (flush + final analysis).
  6. `backend/app/db/models.py` + migration `0014_live_voice_transcripts.py`: `call_transcript_segments`
     (unique `(call_session_id, seq)`) and `call_live_analyses` (versioned snapshots) tables.
  7. `backend/app/repositories/transaction_repository.py`: transcript/analysis persistence + queries.
  8. `backend/app/api/live_voice.py`: authenticated `WS /api/v1/calls/{id}/live` (operator JWT or
     customer token, transaction-scoped), lifecycle/state validation, one-session-per-call +
     concurrency cap, Live-disabled gate; REST `GET /calls/{id}/transcript` (scoped) and
     `GET /calls/{id}/live-analysis` (operator-only) added in `api/customer_dialogue.py`.
  9. `frontend/src/api/liveVoiceClient.ts` + `frontend/public/audio/pcm-capture-worklet.js`: capability
     detection, mic capture → 16 kHz PCM16 resample, WS lifecycle, incremental 24 kHz playback,
     barge-in flush, reconnect/close handling, cleanup, and explicit (non-silent) text fallback.
  10. `frontend/src/App.tsx`: voice path attempts Live when supported + a call session exists, surfaces
      live status/transcript/analysis in an operator panel clearly labeled simulated, and falls back
      explicitly to the existing voice/chat path when Live is unavailable. Browsers without audio
      capture (incl. jsdom tests) never attempt Live, preserving all prior behavior.
- **Security guarantees**: Gemini key stays server-side (never in browser); WS authenticated and
  transaction-scoped (customer tokens cannot reach another transaction's stream); audio frame size,
  queue depth, session duration, and concurrent-session caps enforced; internal analysis is
  operator-only; no secrets/raw audio/full transcripts logged by default.
- **Policy authority**: the transcript/analysis workers never change transaction or call state; only
  the existing deterministic policy/state machine does. Analysis is advisory and isolated — its
  failure degrades to "unavailable" without interrupting voice.
- **Tests** (23 new backend, 1 skipped smoke; 7 new frontend): config validation; grounded analyzer
  (categories, mitigating, escalation rules, no-assistant-mining); orchestrator audio forwarding,
  interim-vs-final persistence + dedup + ordered seq, parallel analysis, analysis-failure isolation,
  termination/cleanup, seq resumption without duplicates; WS auth/disabled/unknown-call/cross-transaction/
  terminal-call/single-session-conflict + full streaming persistence; frontend PCM encode, support
  detection, lifecycle/events/barge-in, mic-denied fallback, policy-code close, graceful end + teardown.
- **Verification Commands & Results**:
  ```bash
  POSTGRES_PORT=5433 uv run pytest              # 341 passed, 1 skipped (live smoke) in ~44s
  uv run ruff check . && uv run ruff format --check .   # clean; 120 files formatted
  uv run mypy app                               # Success: no issues found in 82 source files
  POSTGRES_PORT=5433 make db-verify-migrations  # 0014 upgrade/downgrade/re-upgrade OK
  npm run lint && npm run typecheck && npm run test && npm run build  # 65 passed; build OK
  POSTGRES_PORT=5433 make check-all             # full gate green
  ```
- **Known limitations / risks**: the real Gemini Live path is verified with the mock provider only —
  no live Gemini call was made (no reachable provider in this environment; the previously pasted API
  key is treated as compromised and must be revoked/replaced). Run `GEMINI_LIVE_SMOKE=1` with valid
  credentials to exercise the real handshake (`tests/integration/test_live_voice_smoke.py`). The WS
  concurrency/single-session registry is process-local (fine for a single-instance prototype, not a
  multi-worker deployment). Concurrency correctness is covered by targeted tests, not live load. The
  frontend live audio UI could not be exercised in jsdom; its engine is unit-tested with mocked
  WebSocket/AudioContext/getUserMedia.

---

#### Task P2-A12: Transaction Intelligence, Selective Bank Calls & Gemini Live Configuration Fix
- **Owner / Agent**: Senior Staff Engineer / Full-Stack Architect
- **Status**: `DONE`
- **Objective**: Fix Gemini configuration path, decouple call creation from text-model availability, build a persistent 20-recipient fictional registry, resolve server-controlled recipient risk evidence in `RiskService`, and connect automated risk evaluation to selective bank calls while preventing customer-scoped token initiation.
- **Dependencies**: Tasks P2-A10, P2-A11.
- **Deliverables & Implementation**:
  1. `backend/app/core/config.py`: Explicit repository root and backend directory paths added to `_ENV_FILES`. API key sanitization in `assemble_gemini_api_key` strips surrounding quotes/whitespace and checks `GOOGLE_API_KEY` and `AI_STUDIO_API_KEY` aliases. Missing credentials surface clean errors without leaking secret material.
  2. `backend/app/api/investigations.py`: `get_default_ai_client()` dynamically instantiates `Settings()` to avoid stale singletons when environment variables or `.env` files are updated at runtime.
  3. `backend/app/domain/recipient_registry.py` & `backend/app/db/models.py`: Created `FictionalRecipientModel` mapped to `fictional_recipients` table with exactly 20 demonstration identities: 8 trusted, 5 unknown, and 7 high-risk (spanning mule accounts, rapid fan-in/fan-out collectors, law-enforcement impersonators, and dubious high-yield platforms).
  4. `backend/app/db/migrations/versions/0015_create_fictional_recipients.py`: Alembic migration creating `fictional_recipients` table and pre-seeding all 20 records idempotently.
  5. `backend/app/repositories/recipient_repository.py`: Async repository with `get_by_upi_id`, `get_by_id`, `list_recipients`, and `seed_if_needed()`. Seed integrated into backend lifespan (`main.py`) and test suite setup (`conftest.py`).
  6. `backend/app/services/customer_dialogue_service.py`: Decoupled call session creation from text-model availability when `GEMINI_LIVE_ENABLED=True` and channel is simulated voice, creating calls in `RINGING` status without blocking on text generation. Scalar transaction fields cached upfront to prevent `MissingGreenlet` errors on expired attributes across commits.
  7. `backend/app/services/risk_service.py`: In `assess_transaction`, resolves `recipient_identifier` against the database registry; server-controlled authoritative DB values override client-supplied mock flags (`is_trusted_beneficiary`, `is_flagged_mule`, `account_age_days`, `fan_in_count_24h`, `fan_out_count_24h`).
  8. `backend/app/services/decision_workflow_service.py`: Connected policy decision to selective call initiation. Outbound calls are initiated only when the decision action is `REQUIRE_VERIFICATION`.
  9. `backend/app/api/customer_dialogue.py`: Customer-scoped tokens are forbidden (`403 FORBIDDEN`) from creating call sessions via REST; call initiation is restricted to bank operators or the automated decision workflow.
  10. `frontend/src/App.tsx`: Removed unconditional call creation on payment submission. Payment submission initiates the transaction and waits for `/workflow/evaluate`; only when the policy authorizes intervention (`REQUIRE_VERIFICATION`) does the bank call ring.
  11. `backend/tests/unit/test_recipient_registry.py` & `backend/tests/integration/test_p2_a12_transaction_intelligence.py`: Comprehensive test suites covering registry seeding, lookup, server override of client flags, customer token rejection on call creation, and decoupled call creation.
- **Verification Commands & Results**:
  ```bash
  POSTGRES_PORT=5433 make backend-lint && POSTGRES_PORT=5433 make backend-typecheck # clean
  POSTGRES_PORT=5433 make backend-test                                              # 351 passed, 1 skipped in 45s
  make frontend-lint && make frontend-typecheck && make frontend-test               # 65 passed in 11 test files
  POSTGRES_PORT=5433 make db-verify-migrations                                     # 15 revisions verified up/down/up
  POSTGRES_PORT=5433 make check-all                                                 # 100% full gate pass
  ```
- **Security Notice**: Any Gemini API key previously exposed in conversational context is treated as compromised and must be revoked and regenerated by the repository owner. No secrets are logged or exposed in client payloads.

---

### Phase 3: Customer Portal & Dynamic Intervention UI
- **Task P3-A1**: Simulated Banking Customer Payment Flow & Dynamic Intervention UI (`NOT_STARTED`)

### Phase 4: Fraud Operations Case Management & Audit Console
- **Task P4-A1**: Fraud Operations Case Management & Investigation Console (`NOT_STARTED`)

### Phase 5: End-to-End Scenarios, Hardening & Demonstration
- **Task P5-A1**: End-to-End Integration of the Six Fraud Demo Scenarios (`NOT_STARTED`)
- **Task P5-A2**: Final Security Hardening, Audit Trail Verification & Demo Runbook (`NOT_STARTED`)



