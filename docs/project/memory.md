# Persistent Project Memory: AegisPay AI

## 1. Confirmed Decisions

- **Architecture**: Modular Monolith. All core domains (transactions, risk engine, investigation orchestration) exist within a single deployable backend package with strict internal boundaries.
- **Backend Tech Stack**:
  - Python 3.14 (fully verified compatible with required dependencies).
  - FastAPI + Uvicorn for asynchronous REST API.
  - Pydantic v2 + `pydantic-settings` for typed configuration and request validation.
  - SQLAlchemy 2.x asynchronous ORM with `psycopg` (v3) async driver (`postgresql+psycopg://`).
  - Alembic for database migrations.
  - `uv` for dependency and virtual environment management.
  - Ruff (linting & formatting) and mypy (typechecking).
  - pytest + pytest-asyncio + HTTPX for testing.
- **Frontend UI Prototype Preservation & Reuse**:
  - Inspected `Intent-Check-Fintech-Prototype.zip` supplied by developer.
  - Identified `artifacts/intent-check` as the exact source matching the supplied screenshot (`Aster Bank` / Live payment console with 6-metric summary strip, bank-wide payment activity queue, and interactive customer Android device preview simulator).
  - Preserved the full interactive design, mobile simulator (with voice and chat simulation), scenario switcher (`routine`, `impersonation`, `verified`, `unavailable`, `agent`), drawer inspection panels, and audit event logs.
  - Connected the frontend to the new FastAPI backend health probes (`/health/ready` and `/health/live`) without modifying the core user journeys or rewriting the UI from scratch.
  - Excluded Replit-specific plugins, Express api-server stubs, and Drizzle artifacts.

---

## 2. Repository Conventions

- **Paths**:
  - `backend/app/`: Application source code.
  - `backend/tests/`: Unit and integration test suites.
  - `frontend/src/`: React source code.
  - `docs/project/`: Persistent project governance documents (`prd.md`, `architecture.md`, `rules.md`, `task.md`, `memory.md`).
- **Configuration**:
  - Backend reads `.env` via `app.core.config.Settings`.
  - Frontend reads `VITE_API_BASE_URL` from Vite env vars.
  - Secrets are never committed; safe defaults in `.env.example`.
- **Health Check Conventions**:
  - `GET /health/live`: Fast process liveness check (HTTP 200, no external dependencies).
  - `GET /health/ready`: Database dependency readiness check (`SELECT 1`). Returns HTTP 200 on success, HTTP 503 on failure.

---

## 3. Current Milestone & Status

- **Current Milestone**: Phase 2 — AI Investigation Agent & Multi-Modal Context Analysis (`IN_PROGRESS`).
- **Active Task**: P2-A2.1 (operator authentication & authorization) complete. Ready for next Phase 2/3 task upon user directive.
- **Completed Tasks**:
  - **P1-A1**: Repository foundation, FastAPI backend, Aster Bank frontend prototype preservation, PostgreSQL Docker Compose, Alembic baseline, and health probes.
  - **P1-A2**: 10-state transaction workflow state machine (`INITIATED`, `ASSESSING`, `RISK_ASSESSED`, `DECISION_READY`, `VERIFICATION_REQUIRED`, `HELD_FOR_VERIFICATION`, `INVESTIGATING`, `HUMAN_REVIEW`, `SETTLED_SIMULATED`, `CANCELLED_SIMULATED`), SQLAlchemy models (`TransactionModel`, `TransactionAuditModel`), Alembic migration `0002_create_transactions_and_audits`, transaction repository with optimistic concurrency locking and customer-scoped idempotency, transaction service, Pydantic v2 schemas, REST endpoints (`/api/v1/transactions`), 63 pytest unit/integration tests, and full test isolation on `test_aegispay`.
  - **P1-A3**: Deterministic Risk Engine & Scenario-Driven Assessment. Pure domain evaluation with 11 explainable rules; mandatory guardrails (coercion overrides trusted beneficiary, voice stress is advisory only, missing evidence explicitly tagged as unknown); benchmark scenario fixtures for all 6 demo fraud scenarios; `transaction_assessments` database table with Alembic migration `0003_create_transaction_assessments`; `RiskService` with atomic lifecycle transitions (`INITIATED` -> `ASSESSING` -> `RISK_ASSESSED` -> `DECISION_READY`) and audit trail; REST endpoints `POST /api/v1/risk/evaluate`, `GET /api/v1/risk/scenarios`, `POST /api/v1/transactions/{id}/assess`, and `GET /api/v1/transactions/{id}/assessment`; frontend Aster Bank integration with risk score column, scenario switcher, and dedicated Risk Assessment drawer tab; 100% green test suite (78 backend tests, 9 Vitest frontend tests).
  - **P1-A4**: Risk Engine Verification and Demo Readiness. Verified all 6 scenario fixtures with explainable scores, rules, missing telemetry, and policy actions; confirmed active-call and voice-stress alone never block; verified coercion overrides trusted recipient; confirmed ambiguous signals remain unblocked; clearly separated live backend evaluations (`source: 'backend'`, green pill) from demo fallback (`source: 'demo_fallback'`, amber pill and warning banner); verified clean database migrations (`0001` -> `0002` -> `0003`); added tests for repeated assessments, full transition lifecycle with atomic audits, optimistic locking, and simulated-only state boundaries; 94 total tests (84 backend, 10 frontend) passing with zero failures.
  - **P2-A1**: Gemini-Powered AI Investigation Service & Verification. Integrated official `google-genai` SDK (v2.31.0) with Python 3.14 compatibility; built domain models (`FindingCategory`, `RiskSentiment`, `ConfidenceLevel`, `EvidenceProvenance`), hardened prompt generation with strict anti-prompt-injection fences (`<untrusted_customer_statements>`, `<untrusted_extracted_documents>`), and operational guardrails; created `TransactionInvestigationModel` with Alembic migration `0004_create_transaction_investigations`; implemented `InvestigationService` with comprehensive evidence integrity validation, provenance allowlists, ungrounded fallback to `model_inference`, and anti-injection non-malice invariant; AI client abstraction (`VertexGeminiClient`, `MockGeminiClient`) with configurable `AI_PROVIDER` (`auto`, `vertex_ai`, `gemini_api`, `mock`); exposed REST endpoints (`POST /api/v1/investigations`, `GET /api/v1/investigations/{id}`, `GET /api/v1/transactions/{id}/investigations`); created typed frontend API client (`frontend/src/api/investigationApi.ts`); verified clean database migrations and failure isolation; 121 total tests (111 backend, 10 frontend) passing with zero failures.
  - **P2-A2**: Bounded Multi-Turn Investigation Conversation. Built conversational forensic dialogue layer over existing Gemini and Mock infrastructure; persistent tables `investigation_conversations` and `investigation_conversation_turns` with Alembic migration `0005_create_investigation_conversations`; optimistic concurrency locking on conversation `version`; bounded to 20 turns (`INVESTIGATION_MAX_CONVERSATION_TURNS`) raising HTTP 400 `CONVERSATION_TURN_LIMIT_EXCEEDED`; non-mutating invariant verified (transaction state, version, and audit records remain 100% untouched); cross-transaction isolation enforced (`conversation.transaction_id == transaction_id`); non-repeating targeted follow-up questions; frontend `InvestigationConversationPanel` mounted in `TransactionDrawer` under `'AI Investigation'` tab with turn history, provider badge, risk sentiment, clickable inquiry chips, input composer, and non-mutation advisory; 132 total tests (118 backend, 14 frontend) passing with zero failures.

---

## 4. Confirmed Decisions & Architectural Patterns

- **Task-Tracker Realignment**: In accordance with user requirements, the Deterministic Risk Engine belongs to Phase 1, and the AI Investigation Agent belongs to Phase 2.
- **State Machine Architecture**: Authoritative 10-state workflow lifecycle implemented in `app.domain.state_machine`. Pure domain logic with `validate_transition`, `can_transition`, and `is_terminal`.
- **Deterministic Risk Engine Principles**:
  - Feature evaluation from concrete transaction and evidence inputs only (zero ML / LLM in Phase 1).
  - No scenario IDs, scenario names, or keyword shortcuts in scoring logic.
  - Missing evidence is explicitly captured as unknown, never silently assumed safe or dangerous.
  - Relative risk score (0–100), risk levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and policy recommendations (`ALLOW`, `WARN_CUSTOMER`, `REQUIRE_VERIFICATION`, `HOLD_FOR_INVESTIGATION`, `BLOCK_SIMULATED`).
  - Core guardrail: Trusted recipient status CANNOT override strong coercion indicators. Voice stress alone is NOT proof of fraud.
- **AI Investigation Architecture & Boundaries (Phase 2)**:
  - **Primacy of Deterministic Policies**: The LLM investigates evidence and produces intelligence; it **never** mutates transaction state or bypasses the deterministic state machine.
  - **Evidence Integrity & Provenance Grounding**: Every finding cites concrete evidence references validated against supplied inputs (`stmt_*`, `doc_*`, telephony telemetry, recipient flags, triggered rules). Fabricated/unknown references are rejected and tracked in `missing_information`. Findings with empty or ungrounded evidence references default to `EvidenceProvenance.MODEL_INFERENCE`.
  - **Prompt Injection Defense & Non-Malice Invariant**: Customer statements and document text are treated as untrusted data inside explicit forensic tags (`<untrusted_customer_statements>`, `<untrusted_extracted_documents>`), never as instructions. Adversarial overrides are detected and flagged under `FindingCategory.SOCIAL_ENGINEERING`. Prompt injection in untrusted customer text is treated as manipulation, NEVER as proof of customer malice (`MALICIOUS`).
  - **Multi-Turn Investigation Dialogue Invariants (P2-A2)**:
    - Bounded to `INVESTIGATION_MAX_CONVERSATION_TURNS = 20`. Exceeding limit raises HTTP 400 `ConversationTurnLimitError`.
    - Strict cross-transaction isolation: any access or turn addition to a conversation associated with a mismatched transaction ID immediately yields HTTP 404 `RESOURCE_NOT_FOUND`.
    - Transaction State & Audit Invariance: Conversation initialization and turn submissions execute inside independent transactional boundaries without altering transaction `state`, `version`, or appending to `transaction_audits`.
    - Contextual Memory & Anti-Repetition: Assistant turns analyze complete prior turn history and generate distinct, decision-relevant follow-up prompts that omit inquiries already resolved.
    - Idempotency & Concurrency: Client turns support optional `client_turn_id` idempotency token (enforced since the 2026-10-17 audit via a replay check in `submit_conversation_turn`: a repeated token returns current state instead of appending duplicate turns); conversation updates verify optimistic locking version increment. Turn ordering is protected at the DB level by `uq_conversation_turn_index` (unique on `conversation_id, turn_index`), which also bounds the 20-turn limit under concurrent inserts.
    - Prompt History Fidelity (audit lesson): conversation-history dicts passed to `build_conversation_investigation_prompt` MUST use keys `turn_index` and `evidence_provenance` (the builder reads those). A prior key mismatch (`provenance`, no `turn_index`) rendered every historical turn as `index="0" provenance="none"` — content was still passed, only labels were wrong.
  - **Provider Selection & Credential Transparency**: Controlled via `AI_PROVIDER` setting (`auto`, `vertex_ai`, `gemini_api`, `mock`). Metadata explicitly reports `"mock_gemini"` vs `"vertex_ai"`; mock outputs are never misrepresented as live AI findings. Missing credentials on live providers raise HTTP 503 `AI_CONFIGURATION_ERROR`.
  - **Authentication & Authorization (P2-A2.1, implemented)**: Operations-console routes require an authenticated **operator** via `get_current_operator` ([ADR-002](../decisions/ADR-002-operator-authentication.md)). Login (`POST /api/v1/auth/login`) validates a bcrypt hash in the `operators` table (migration `0006`) and issues a short-lived HS256 **Bearer JWT** (`AUTH_JWT_SECRET`, fail-closed). Authorization model is **operator-shared** (any active operator may access any case, matching the bank-wide console persona); transaction-scoped conversation routes also enforce `conversation.transaction_id == transaction_id`. `/auth/login` and `/health/*` are public. Demo login is provisioned on startup from `AUTH_BOOTSTRAP_OPERATOR_USERNAME`/`_PASSWORD` (idempotent). Libraries: `PyJWT`, `bcrypt` (no custom crypto). Frontend gates the console behind an `AuthGate` login screen and sends the token via a shared `apiFetch` wrapper that forces logout on 401.
  - **Former blocker (now resolved for the operator model)**: the prior "no authentication / IDOR" deployment blocker from the P2-A2 audit is closed. Remaining future work (not blockers for a private demo): per-operator audit attribution, role tiers, token revocation/refresh, `/auth/login` rate limiting, external IdP for production multi-tenant use.
  - **Auth hardening (security review of `777fae8`)**: JWT decode now *requires* `exp` and `sub` (a token lacking `exp` is rejected, not treated as non-expiring); algorithm allowlist already rejects `alg=none` and HS512/HS256 confusion. Login uses a real bcrypt hash for the unknown-user path so timing does not reveal account existence (response text was already identical). Durable rule: when adding a timing-equalization fallback, the fallback hash MUST be a valid bcrypt hash or `verify_password` short-circuits and the defense is void. **Not public-production ready**: `/auth/login` still has no rate limiting/lockout; HTTPS/TLS and per-environment `CORS_ORIGINS` + strong `AUTH_JWT_SECRET` are deployment requirements.
  - **Confidence Calibration**: Qualitative confidence score (0.0 to 1.0) reflects model assessment certainty, not calibrated statistical fraud probability.
- **Idempotency Strategy**: Scoped per `(customer_id, idempotency_key)` backed by PostgreSQL unique constraint and canonical SHA-256 payload hash.
- **Concurrency Control**: Optimistic version locking via integer `version` incremented on each state change.
- **Audit Integrity**: Append-only `transaction_audits` recorded atomically in the same database transaction.
- **Risk Assessment History**: Persisted in `transaction_assessments` table, retaining complete input snapshot, triggered rules, supporting evidence, and missing evidence.
- **Investigation History**: Persisted in `transaction_investigations` table, linked to transactions and optional deterministic assessments (`ondelete="SET NULL"`).
- **Conversation History**: Persisted in `investigation_conversations` and `investigation_conversation_turns` tables with foreign keys and cascaded lifecycle.

---

## 5. Next Phase / Tasks (Awaiting User Directive)

- **Phase 2 Continuation**: Multi-Modal AI Investigation Agent & Voice Duress Analysis.
  - P2-A3: Real-time voice interview / duress analysis integration.
- **Phase 3**: Customer Portal & Dynamic Intervention UI.
  - P3-A1: Simulated Banking Customer Payment Flow & Dynamic Intervention UI.


