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

#### Task P2-A3: Gemini Real-Time Voice Duress & Psychological Analysis Agent (`NOT_STARTED`)

---

### Phase 3: Customer Portal & Dynamic Intervention UI
- **Task P3-A1**: Simulated Banking Customer Payment Flow & Dynamic Intervention UI (`NOT_STARTED`)

### Phase 4: Fraud Operations Case Management & Audit Console
- **Task P4-A1**: Fraud Operations Case Management & Investigation Console (`NOT_STARTED`)

### Phase 5: End-to-End Scenarios, Hardening & Demonstration
- **Task P5-A1**: End-to-End Integration of the Six Fraud Demo Scenarios (`NOT_STARTED`)
- **Task P5-A2**: Final Security Hardening, Audit Trail Verification & Demo Runbook (`NOT_STARTED`)

