# Agent Operational Rules & Development Standards

These rules are **mandatory** for all coding agents and engineers working on the AegisPay AI codebase. Violations of these rules compromise system safety, security, and project velocity.

---

## 1. Pre-Task Protocol (Mandatory Step 0)

Before modifying any code or creating new files, every agent **MUST**:
1. Read all five project documents in `docs/project/`:
   - `prd.md`
   - `architecture.md`
   - `rules.md`
   - `task.md`
   - `memory.md`
2. Inspect the current Git repository state (`git status`, `git diff`) and existing relevant source code.
3. Verify the assigned task's dependencies, current status, and acceptance criteria in `docs/project/task.md`.
4. Identify any discrepancies or conflicts between current instructions and established architecture before proceeding. Do NOT silently override approved product or architectural patterns.

---

## 2. Code Quality & Verification Rules

1. **Verify Before Declaring Complete**: Never mark a task `DONE` or claim functionality works without running actual verification commands and reporting the output.
2. **Strict Static Typing**:
   - Backend: All Python code must be fully type-hinted and pass `mypy app` with zero errors.
   - Frontend: All TypeScript code must pass `tsc --noEmit` with zero errors.
3. **Automated Linting & Formatting**:
   - Backend: Must pass `ruff check .` and `ruff format --check .`.
   - Frontend: Must pass `npm run lint`.
4. **Comprehensive Test Suite**:
   - Every new feature, endpoint, or domain service must include automated unit/integration tests.
   - Tests must pass cleanly with `pytest` (backend) and `npm run test` (frontend).

---

## 3. Security & Simulation Boundary Rules

> [!CAUTION]
> **Strict Prohibitions**:
> 1. **No Committed Secrets**: Never hardcode or commit database credentials, API keys, tokens, or private certificates into version control. Use `.env.example` with harmless placeholders.
> 2. **No Real Banking or Payment Rails**: Never integrate with live UPI, NPCI, SWIFT, real banking APIs, live SMS gateways, or real WhatsApp Business accounts. All rails and third-party data providers must remain simulated.
> 3. **No Hardcoded Scenario Shortcuts**: Never hardcode fraud scores, risk outputs, or decision branches conditioned directly on test case IDs or scenario titles (e.g., `if scenario_id == 'scenario_1': return 'BLOCK'`). All evaluations must evaluate actual transaction features, signals, and policies.
> 4. **No Fabricated Evidence**: AI investigation outputs must be grounded in actual conversation prompts, uploaded document context, and transaction metadata.

---

## 4. Architectural Integrity Rules

1. **Modular Monolith**: Maintain clean modular boundaries. Do not split the repository into standalone microservices or separate deployables without formal ADR approval.
2. **Thin API Layer**: FastAPI routers handle only HTTP input validation, status codes, dependency injection, and response serialization. All orchestration belongs in application services; business rules belong in domain models.
3. **Centralized Configuration**: All configuration must reside in `app.core.config.Settings` via `pydantic-settings`. Do not call `os.getenv` directly within business logic.
4. **Structured Error Handling**: Never expose raw database errors, stack traces, or internal server details to HTTP clients. Use structured error envelopes.
5. **Database Discipline**: Never place domain business logic inside ORM models. Schema migrations must be managed through versioned Alembic scripts.

---

## 5. Post-Task Protocol (Mandatory Step Last)

At the conclusion of every agent task:
1. Run and record the complete test suite and linters.
2. Update `docs/project/task.md`:
   - Set task status (`DONE`, `BLOCKED`, etc.).
   - Record exact verification results and test outputs.
   - Clearly define the next recommended task.
3. Update `docs/project/memory.md` with newly confirmed decisions, patterns, or known issues.
4. Update `docs/project/architecture.md` or `docs/project/prd.md` if any system interfaces or product requirements evolved.
5. Provide a concise, factual summary of changes to the user without redundant recitation of documentation files.
