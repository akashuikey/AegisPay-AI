AegisPay AI --- Agent Operational Rules & Engineering Standards
Status: Mandatory
Applies to: Every human contributor and coding agent
Authority: These rules govern implementation quality and agent
workflow. Product requirements are defined in prd.md; system design is
defined in architecture.md; task status is maintained in task.md;
durable project context is maintained in memory.md.
The objective is to build AegisPay AI as a secure, maintainable,
testable product quickly---without sacrificing correctness or creating
unnecessary abstractions. These rules are mandatory unless an explicit,
documented decision supersedes a specific rule.
1. Core Engineering Principles
1. Correctness before cleverness. Prefer clear, predictable code
   over clever tricks, excessive indirection, or premature
   optimization.
2. Reuse with judgment. Reuse genuinely shared behavior. Do not
   force unrelated behavior into a common abstraction merely to avoid a
   few repeated lines.
3. Simple first, extensible where justified. Implement the smallest
   design that satisfies current requirements while preserving clear
   boundaries for known future work.
4. One source of truth. Avoid duplicate business rules,
   configuration, state, schemas, constants, and documentation that can
   drift apart.
5. Explicit over implicit. Make dependencies, side effects, state
   changes, errors, and assumptions visible.
6. Fail safely. Validate untrusted inputs, handle expected failures
   deliberately, and never silently convert errors into success.
7. Evidence over claims. Code, tests, logs, and verification
   results must support claims that a feature works.
8. No speculative engineering. Do not build generic frameworks,
   plugin systems, factories, registries, base classes, or extension
   points without a demonstrated requirement.
9. Maintainable delivery. A task is not complete merely because
   code was generated; it must be integrated, verified, documented
   where needed, and understandable to the next contributor.
10. Preserve working product behavior. Inspect the existing
    implementation before changing it. Avoid unrelated rewrites and
    preserve the approved UI and user journey unless the task explicitly
    requires a change.
2. Mandatory Pre-Task Protocol
Before changing code, configuration, tests, or project documents, every
agent MUST:
1. Read all five files in docs/project/:
   - prd.md
   - architecture.md
   - rules.md
   - task.md
   - memory.md
2. Inspect the repository and current Git state:
   - git status
   - Relevant git diff output
   - Relevant files, tests, configuration, and existing patterns
3. Confirm the assigned task, dependencies, acceptance criteria, and
   current status in task.md.
4. Identify affected modules, API contracts, database schemas, and
   consumers before changing interfaces.
5. Check whether the task is already implemented wholly or partially;
   do not duplicate existing functionality.
6. Identify conflicts with approved product or architecture decisions.
   Ask for clarification when a material conflict cannot be resolved
   from the documents.
7. State a brief implementation plan for substantial tasks before
   making broad changes.
8. Keep changes within the assigned scope. Do not silently begin the
   next task.
Do not overwrite unrelated user changes, reset the repository,
force-push, or run destructive commands without explicit authorization.
3. Object-Oriented Design and Abstraction Rules
Use object-oriented programming where it improves cohesion,
encapsulation, substitutability, or lifecycle management. OOP is a
design tool, not a requirement to turn every function or data structure
into a class.
3.1 When to create a class
Create a class when at least one meaningful reason exists, such as:
- It represents a domain concept with identity, invariants, or
  behavior.
- It encapsulates state and the operations that maintain that state.
- It manages a resource lifecycle, such as a database session or
  external client.
- It provides a cohesive service with several related operations and
  dependencies.
- It implements a real interchangeable strategy or adapter behind a
  useful interface.
- It consolidates behavior that is genuinely shared by multiple
  callers.
Prefer a plain function for a stateless, focused operation. Prefer a
dataclass or Pydantic model for data that does not need a behavioral
class. Do not create a class solely to wrap one trivial function.
3.2 Reuse repeated behavior deliberately
- Before adding repeated logic, search for an existing implementation
  that already solves the same problem.
- If multiple callers need the same stable behavior, extract it into a
  well-named shared function, service, component, or module.
- If multiple integrations share meaningful lifecycle or behavior,
  consider a common client or adapter with a small, cohesive
  interface.
- If several services need the same database operations, use shared
  repository utilities or a base repository only when the operations
  and semantics are genuinely common.
- Prefer composition and dependency injection over deep inheritance.
- Avoid copy-pasting complex validation, error handling,
  serialization, query construction, retry logic, or configuration
  handling.
- Do not prematurely generalize two superficially similar operations
  that have different business semantics.
- Do not introduce a "utils" dumping ground. Place shared behavior in
  a module named for its responsibility.
3.3 Base classes and inheritance
- Create a base class only when it defines a real contract or
  implements behavior that subclasses can safely share.
- Subclasses must honor the base class's documented behavior and
  expectations.
- Avoid deep inheritance hierarchies, marker-only base classes, and
  overrides that break expected behavior.
- Do not create BaseManager, BaseService, BaseRepository, or
  similar abstractions automatically. Introduce them only when
  concrete repeated behavior and multiple meaningful consumers justify
  them.
- Do not build abstractions for hypothetical future requirements.
3.4 Class and function size
- Each class and function should have one clear responsibility.
- Split code when a unit has multiple independent reasons to change,
  becomes difficult to test, or obscures the main workflow.
- Do not split code into many tiny functions that add indirection
  without improving clarity, reuse, testing, or naming.
- Do not place an entire workflow into one enormous function or class.
- Keep related behavior close together and keep unrelated concerns
  separate.
- Prefer dependency injection for external dependencies rather than
  constructing hidden clients throughout business logic.
3.5 Practical decision test
Before introducing an abstraction, ask:
1. Is this behavior used more than once, or is there a concrete
   requirement for an interchangeable implementation?
2. Does the abstraction reduce duplication or clarify a boundary?
3. Can its name and contract be explained simply?
4. Will it make testing or future changes easier?
5. Is its cost lower than the complexity it introduces?
If the answer is mostly no, use the simpler implementation.
4. No-Hardcoding Rules
Hardcoding means embedding values that should be configurable, derived
from authoritative data, or maintained centrally.
1. Do not hardcode credentials, tokens, private keys, connection
   strings containing secrets, or environment-specific endpoints.
2. Centralize environment-dependent configuration using
   app.core.config.Settings and pydantic-settings.
3. Keep safe local defaults where appropriate; provide .env.example
   with harmless placeholders.
4. Do not scatter repeated business thresholds, time windows, limits,
   status strings, model names, feature weights, or policy values
   throughout the code.
5. Put business policy values in a clear, typed and appropriately
   configurable policy/configuration module. Do not make every constant
   an environment variable---only expose settings that reasonably need
   runtime/environment-specific changes.
6. Use enums or constrained types for stable finite sets of statuses
   and categories where appropriate.
7. Derive transaction risk from actual transaction features, recipient
   intelligence, available signals, and explicit policy rules.
8. Never use scenario_id, scenario title, customer name, or a fixture
   identifier as a shortcut for a risk score, fraud label, or decision.
9. Scenario fixtures may choose the input data for a test or demo; the
   normal assessment pipeline must process those inputs through the
   same feature extraction, scoring, and decision logic.
10. Do not hardcode fake successful responses to make the UI appear
    connected. The frontend must reflect actual backend responses and
    failures.
11. Do not duplicate data that can be obtained reliably from an
    authoritative source within the application. If data is
    intentionally snapshotted, document why and how it stays consistent.
12. Keep magic numbers out of complex expressions. Give meaningful names
    to non-obvious constants and explain policy-sensitive values.
13. Never fabricate model findings, transaction evidence, recipient
    histories, document verification, or external integration results.
5. Python and Backend Standards
5.1 General Python quality
- Use type hints for public functions, methods, parameters, return
  values, and important data structures.
- Code must pass the configured mypy app check with zero errors,
  except for an explicitly documented and narrowly scoped temporary
  exception approved by the project owner.
- Avoid Any; when unavoidable at untyped boundaries, validate or
  narrow the type before using the value.
- Use clear names, small cohesive modules, and standard Python
  conventions.
- Follow Ruff linting and formatting rules.
- Prefer standard-library functionality over new dependencies when it
  is sufficient.
- Add a dependency only when it provides clear value; pin or constrain
  versions using the project's dependency-management strategy.
- Do not suppress type or lint errors broadly. Any suppression must be
  narrow and justified.
5.2 Functions and side effects
- Functions should have a clear contract and predictable return
  behavior.
- Avoid hidden network calls, database writes, or state changes inside
  functions that appear to be pure transformations.
- Keep pure calculations separate from I/O when that separation
  improves testability.
- Avoid excessive optional parameters, boolean flags that change a
  function's meaning, and functions with unrelated responsibilities.
- Do not use mutable default arguments.
- Do not catch exceptions merely to log and re-raise without adding
  value.
- Do not use broad except Exception handlers unless they form a
  deliberate application boundary with safe handling and appropriate
  logging.
- Never swallow errors silently.
- Use retries only for transient failures, with bounded attempts and
  suitable backoff. Do not retry non-idempotent operations blindly.
5.3 Async and concurrency
- Use async database and HTTP clients consistently with the
  asynchronous application stack.
- Do not block the event loop with synchronous network or file
  operations in async request handlers.
- Use a thread/process executor or an asynchronous alternative when
  blocking work must be performed.
- Do not create unbounded background tasks or unbounded concurrent
  LLM/API requests.
- Apply timeouts and resource limits to external calls.
- Manage client, session, and connection lifecycles centrally where
  appropriate.
5.4 FastAPI and API boundaries
- Routers handle HTTP concerns: request validation,
  authentication/authorization dependencies, status codes, and
  response serialization.
- Application services coordinate workflows; domain logic belongs in
  domain models or focused policy functions/modules.
- Reuse request/response schemas where the same contract is genuinely
  shared. Do not reuse one schema indiscriminately for unrelated API
  operations.
- Use explicit response models and meaningful HTTP status codes.
- Version public APIs under /api/v1.
- Validate all client-supplied input. Never trust client-supplied risk
  scores, recipient classifications, permissions, transaction states,
  or authoritative fraud indicators.
- Keep error responses structured and consistent. Do not expose stack
  traces, SQL details, secrets, or internal prompts.
- Apply request size, upload type, timeout, and rate limits where
  appropriate to the risk of the endpoint.
- Make retryable mutation endpoints idempotent when required by their
  contract.
6. Database and Persistence Standards
1. Use SQLAlchemy 2.x patterns and the project's configured
   asynchronous PostgreSQL driver.
2. Keep persistence concerns in repositories or clearly defined
   data-access modules; keep business policy out of ORM models.
3. Use Alembic for all schema changes. Never rely on production
   create_all() calls to manage schema evolution.
4. Every migration must be reviewed for correctness, ordering,
   data-loss risk, and reversibility where practical.
5. Use foreign keys, unique constraints, check constraints, and indexes
   when they express real integrity or query requirements.
6. Use transactions for logically atomic changes.
7. Avoid N+1 queries, unbounded table scans, unnecessary round trips,
   and loading entire datasets when only a subset is needed.
8. Use pagination or bounded result sets for potentially large
   collections.
9. Define and handle database transaction boundaries explicitly.
10. Do not share an AsyncSession unsafely across concurrent tasks.
11. Store timestamps consistently, preferably as timezone-aware UTC
    values, and convert to local time at presentation boundaries.
12. Use decimal-safe representations for monetary amounts; do not use
    binary floating-point for authoritative currency arithmetic.
13. Never build SQL using unsafe string interpolation with user input.
    Use parameterized queries.
14. Do not log database credentials or sensitive query parameters.
15. Cloud SQL/PostgreSQL is the authoritative store for application
    transaction state. BigQuery, if introduced, is for analytics and
    historical evaluation---not synchronous transaction-state authority.
7. Frontend and UI Standards
1. Use TypeScript types for API payloads, component props, state, and
   important domain objects. Avoid any; prefer unknown with
   validation at uncertain boundaries.
2. Run TypeScript checks with zero errors.
3. Reuse shared UI components when they have stable, repeated behavior
   or presentation.
4. Do not build a component library or generalized design system for
   one-off elements without a concrete need.
5. Keep components focused. Extract hooks or child components when
   doing so improves readability, reuse, or testability---not simply to
   reduce line count.
6. Keep API communication in a consistent client/service layer rather
   than duplicating raw fetch logic throughout unrelated components.
7. Handle loading, empty, success, validation-error, network-error, and
   retry states where relevant.
8. Do not claim an operation succeeded before the backend confirms it.
9. Do not calculate authoritative risk scores or transaction decisions
   independently in the frontend.
10. Treat frontend configuration as public. Never place API keys,
    secrets, or privileged credentials in Vite-exposed variables.
11. Preserve the approved AegisPay UI and demo journey. Modify the
    existing prototype incrementally rather than redesigning it from
    scratch without approval.
12. Ensure forms are accessible, labels are meaningful, keyboard
    navigation works, and status is not conveyed by color alone.
13. Avoid unnecessary global state. Keep state near its owner until
    sharing across components is genuinely required.
14. Do not add frontend dependencies without explaining their purpose
    and checking compatibility.
8. Testing and Verification Standards
8.1 Required quality gates
Before marking a task complete, run the applicable checks and report
actual results:
Backend - uv run pytest - uv run ruff check . -
uv run ruff format --check . - uv run mypy app
Frontend - npm run lint - npm run typecheck or the configured
equivalent, such as tsc --noEmit - npm run test when the test script
is configured - npm run build
Use the actual project scripts and document any differences. Do not
invent successful output.
8.2 Test design
- Add tests for new behavior, bug fixes, API endpoints, domain
  policies, and non-trivial service logic.
- Test normal behavior, boundary conditions, invalid input, and
  relevant failure paths.
- Unit-test deterministic business rules without requiring live cloud
  services.
- Use integration tests for database behavior and API/service
  integration.
- Use end-to-end tests for important customer journeys when practical.
- Keep tests deterministic and isolated. Do not depend on network
  services, wall-clock timing, or real credentials unless the test is
  explicitly an integration test designed for that dependency.
- Use fixtures and factories to reduce repetitive test setup; avoid
  building a complex test framework for a handful of tests.
- Test externally visible behavior rather than private implementation
  details wherever practical.
- A test that merely asserts True, mocks the entire behavior under
  test, or only verifies that a method was called is insufficient for
  meaningful business logic.
- Never delete or weaken a failing test just to make a check pass
  without understanding and documenting the underlying issue.
8.3 Honest verification
- Distinguish checks that passed, failed, were skipped, or could not
  run.
- If a dependency or environment is unavailable, report that
  limitation and run the remaining feasible checks.
- Do not report a service as working based only on code inspection.
- Do not mark acceptance criteria complete unless evidence supports
  them.
9. Security, Privacy, and Simulation Boundaries
9.1 Prohibitions
- Never commit secrets, credentials, tokens, certificates, local
  .env files, or sensitive datasets.
- Never integrate real bank APIs, live UPI/NPCI payment rails, SWIFT,
  real payment settlement, live SMS gateways, or real WhatsApp
  Business accounts in this prototype.
- Never claim a real transfer was blocked, held, frozen, refunded, or
  recovered.
- Use clearly labeled simulated states such as HELD_FOR_VERIFICATION
  and communicate that a simulated pre-settlement hold is not a real
  banking action.
- Never claim access to real phone calls, screen sharing, GPS,
  clipboard contents, device telemetry, or other private device
  activity. Such signals must be simulated or explicitly supplied by
  the user in this prototype.
- Never treat stress, voice tone, a first-time payee, or a large
  payment alone as proof of fraud.
- Never claim OCR or document extraction establishes authenticity.
  Mark documents UNVERIFIED unless independent verification exists.
- Never allow model-generated output to execute arbitrary code, SQL,
  shell commands, or unrestricted tools.
9.2 Application security
- Validate and constrain untrusted input at system boundaries.
- Apply authentication and authorization before protecting real
  user-specific or operator-only data; never rely on frontend hiding
  as access control.
- Use least privilege for service accounts, database roles, and
  external integrations.
- Avoid logging sensitive personal, financial, authentication, or
  document data unless strictly necessary and approved.
- Sanitize untrusted content before rendering it as HTML or passing it
  to tools.
- Treat user-provided messages, transcripts, uploaded documents, and
  retrieved content as untrusted data---not as instructions that
  override system policy.
- Protect file uploads with size/type validation and safe storage
  practices.
- Do not expose internal prompts, credentials, stack traces, or
  infrastructure details to clients.
- Apply secure defaults for CORS, cookies, transport security, and
  secrets management as deployment requirements become applicable.
10. AI, Agents, and Decision Policy Rules
1. Use deterministic code for deterministic operations: validation,
   feature calculation, thresholds, state transitions, authorization,
   and policy enforcement.
2. Use LLMs for tasks where language understanding or contextual
   reasoning adds value, such as analyzing supplied messages and
   transcripts or explaining evidence.
3. Treat model output as untrusted, schema-validate it, and handle
   missing, malformed, contradictory, or unsupported findings.
4. Require evidence provenance for investigative claims: identify the
   source and quote or reference the relevant supplied content when
   possible.
5. Distinguish observations, inferences, confidence, and unknowns. Do
   not present uncertainty as fact.
6. Do not invent transcript content, document fields, recipient
   history, external verification, or customer intent.
7. An LLM may recommend an action, but it must not directly mutate
   authoritative transaction state. The deterministic
   policy/application service validates and applies permitted
   transitions.
8. Keep model prompts, model configuration, output schemas, timeouts,
   and error handling centralized in appropriate modules. Do not
   scatter near-identical prompts across endpoints.
9. Do not add an agent for every small task. Prefer a normal function
   or tool for deterministic work and introduce a separate agent only
   when autonomous/contextual reasoning and a distinct responsibility
   justify it.
10. Avoid multi-agent orchestration where a single well-defined workflow
    is sufficient.
11. Apply timeouts, bounded retries, token/input limits, and graceful
    degradation to model calls.
12. Never assume a model's confidence is a calibrated probability. Label
    confidence appropriately unless calibration has been validated.
13. Missing evidence is not evidence of fraud or safety. Represent
    missingness explicitly and make policy behavior clear.
14. Trusted recipients can reduce recipient uncertainty but must not
    override strong evidence of coercion.
15. Do not expose chain-of-thought or hidden internal reasoning. Return
    concise, evidence-grounded explanations and structured findings
    suitable for the user or operator.
11. Transaction State and Audit Integrity
1. Maintain one authoritative transaction state in the backend
   database.
2. Define permitted state transitions explicitly; reject invalid
   transitions.
3. Ensure only authorized application services can apply consequential
   state transitions.
4. Use database transactions and concurrency controls where needed to
   prevent inconsistent updates.
5. Use idempotency keys for payment-initiation or other mutation
   operations where retries could create duplicate transactions.
6. Record meaningful state changes and decisions in an audit trail with
   timestamps, source, actor/system component, and decision rationale
   where appropriate.
7. Do not silently overwrite audit history. Corrections should be
   represented in a traceable manner.
8. Keep frontend display state synchronized with backend results; do
   not let separate UIs maintain conflicting authoritative transaction
   state.
9. Separate risk assessment from the final policy decision. A risk
   score or AI recommendation is not itself a transaction state
   transition.
10. Treat duplicate events, delayed responses, timeouts, and retried
    requests as normal conditions to handle deliberately.
12. Dependencies, Configuration, and Infrastructure
- Keep dependency lists purposeful and remove unused dependencies.
- Do not add a new library for functionality already adequately
  provided by the current stack without a clear reason.
- Pin or constrain dependency versions consistently with the project
  toolchain.
- Keep configuration typed, validated and centralized.
- Do not duplicate environment-specific values across source files, CI
  configuration and deployment manifests.
- Keep local setup reproducible through documented commands and
  checked-in configuration templates.
- Do not add infrastructure services merely to make the architecture
  look more sophisticated.
- Introduce cloud services only when a specific requirement justifies
  their cost, complexity, and operational burden.
- Do not introduce microservices without an approved ADR explaining
  the need, boundaries, deployment consequences and trade-offs.
- Ensure CI executes the same essential quality gates used locally.
13. Git and Change Management
1. Keep changes focused on the assigned task.
2. Inspect git diff before finalizing to catch unrelated changes,
   accidental deletions, generated files, secrets, and debugging code.
3. Do not overwrite user changes or revert unrelated work.
4. Do not commit generated artifacts, local databases, virtual
   environments, build output, caches, or credentials unless explicitly
   required.
5. Use clear, descriptive commit messages when commits are requested or
   part of the workflow.
6. Update API contracts and documentation when interfaces or important
   behavior change.
7. Record significant architectural choices as ADRs, including context,
   decision, alternatives and consequences.
8. Do not silently introduce breaking API or schema changes. Identify
   affected consumers and update tests and documentation.
9. Do not claim a commit, push, deployment, or merge occurred unless it
   actually did.
14. Project Documentation and Agent Memory
The authoritative project documents live in docs/project/:
- prd.md: product requirements and scope.
- architecture.md: system architecture and approved design
  decisions.
- rules.md: mandatory engineering and agent rules.
- task.md: task backlog, dependencies, status and verification
  results.
- memory.md: concise durable project context, confirmed decisions,
  lessons and known issues.
At the start of every task
Read all five documents and inspect the repository. Resolve conflicts
explicitly rather than silently changing approved decisions.
At the end of every task
1. Run applicable tests, linters, type checks and builds.
2. Review the final diff.
3. Update task.md with the actual status, verification outcomes,
   blockers and next recommended task.
4. Update memory.md with meaningful new decisions, conventions,
   lessons or known issues.
5. Update architecture.md or prd.md only when their authoritative
   content changes.
6. Update rules.md only for intentional project-wide rule changes.
7. Record ADRs for material architecture decisions.
8. Provide the user with a concise summary of implemented changes,
   verification results and remaining limitations.
Use DONE only when all applicable acceptance criteria have been
verified. Use BLOCKED when an unresolved dependency prevents
completion. Do not represent partially implemented work as complete.
Keep these documents concise, specific and internally consistent. Do not
copy the entire same content into multiple documents.
15. Task Execution and Scope Discipline
- Implement one assigned task at a time.
- Break substantial tasks into small, reviewable changes.
- Establish clear acceptance criteria before implementation.
- Prefer vertical slices that deliver a working capability over
  disconnected layers of unfinished code.
- Do not begin dependent tasks before the current task reaches its
  agreed completion gate.
- When requirements are ambiguous, ask a focused question if the
  ambiguity materially affects behavior, security, data design, or
  architecture. Otherwise make a conservative choice and document it.
- If a task reveals a necessary architecture change, explain the
  reason and trade-offs before making a material deviation.
- Do not conceal shortcuts, temporary implementations, missing tests,
  or known defects.
- Avoid unnecessary status updates; prioritize working code, evidence,
  and concise reports.
16. Definition of Done
A task is complete only when all applicable conditions are satisfied:
- [ ] Acceptance criteria are implemented.
- [ ] Changes fit the approved architecture and project rules.
- [ ] New behavior has meaningful automated tests.
- [ ] Applicable tests pass.
- [ ] Linting, formatting, and static type checks pass.
- [ ] Frontend builds and/or backend starts when relevant.
- [ ] Errors, edge cases, and security boundaries are handled
  appropriately.
- [ ] No secrets, debug artifacts, or unrelated changes are included.
- [ ] API contracts, migrations, and documentation are updated when
  required.
- [ ] task.md and memory.md reflect the actual result.
- [ ] Verification results and remaining limitations are reported
  honestly.
If any applicable condition is unmet, report the task as incomplete or
blocked rather than claiming full completion.
17. Rule Changes and Exceptions
These rules may be changed only deliberately, not bypassed silently.
- A task-specific exception must be explicit, narrowly scoped,
  justified, and documented in the relevant task or ADR.
- Security, simulation-boundary, data-integrity, and
  truthful-verification prohibitions cannot be waived merely for demo
  convenience.
- If two instructions conflict, prioritize safety and data integrity,
  then the approved product requirements and architecture. Ask the
  project owner when the conflict remains material.
- Update this document when a rule changes so future agents follow the
  same standard.
Final principle: Build the simplest maintainable solution that
satisfies the requirement, reuse shared behavior where it is genuinely
shared, avoid abstractions without purpose, and prove correctness
through tests and observable behavior.