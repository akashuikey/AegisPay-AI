# ADR-002: Operator Authentication & Authorization Boundary

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Senior Architect / Full-Stack Engineer (P2-A2.1)

---

## Context and Problem Statement

Through P2-A2 the operations-console API (transactions, risk, investigations, and
investigation conversations) was reachable with no identity verification. The
P2-A2 audit confirmed that any client with a resource UUID could read or write
investigation conversations, and that the `/api/v1/conversations/{id}` routes had
no scoping at all. The relationship check `conversation.transaction_id == transaction_id`
is cross-transaction isolation, not authentication.

We need a minimal, real, server-validated authentication and authorization
boundary that fits the existing architecture (cross-origin React SPA → FastAPI,
PostgreSQL, pydantic-settings) and keeps the demo usable, without introducing a
heavyweight identity platform.

## Decision

1. **Principal = operator (fraud-operations analyst).** The console is a bank-wide
   operations tool whose persona reviews all customers' flagged transactions, so
   the authenticated identity is an operator, not a payer. Authorization model is
   **operator-shared**: any authenticated, active operator may access any case.
   Object-level control reduces to "must be an authenticated operator", plus the
   existing transaction-scoping check on transaction-scoped conversation routes.

2. **Transport = Bearer JWT.** Login returns a short-lived HS256 JWT signed with
   `AUTH_JWT_SECRET`; the SPA sends it as `Authorization: Bearer`. Chosen over
   cookies because the SPA is cross-origin to the API, which avoids SameSite/CSRF
   complexity for the prototype. Trade-off: the token is readable by JS (XSS),
   mitigated by a short lifetime (default 60 min) and no long-lived secret stored
   client-side.

3. **Credential store = `operators` table + env bootstrap.** A new `operators`
   table (migration `0006`) holds `username` + bcrypt `password_hash`. A bootstrap
   operator is provisioned on startup from `AUTH_BOOTSTRAP_OPERATOR_USERNAME` /
   `AUTH_BOOTSTRAP_OPERATOR_PASSWORD` (plaintext read only from env, stored solely
   as a bcrypt hash; idempotent — never resets an existing operator).

4. **Libraries:** `PyJWT` for tokens, `bcrypt` for hashing. No custom cryptography.

5. **Fail closed:** `AUTH_JWT_SECRET` has no insecure default; token issue/verify
   raises `AUTH_CONFIGURATION_ERROR` (503) when it is unset. Credential and token
   failures return `401 UNAUTHENTICATED` with a generic message (no account
   enumeration, no detail leakage).

6. **Enforcement point:** the dependency `get_current_operator` is attached at
   router-include time to the transactions, risk, investigations, and conversations
   routers, uniformly gating every route (including the previously unscoped
   `/conversations/{id}` routes). `/auth/login` and `/health/*` remain public.

## Alternatives Considered

- **HttpOnly cookie session** — stronger against XSS token theft, but cross-origin
  cookies need `SameSite=None; Secure` (HTTPS) plus CSRF defense; more moving parts
  than warranted for the prototype.
- **Per-owner resource scoping** — stricter isolation, but conflicts with the
  bank-wide operations-console persona/UI and adds ownership plumbing with no
  current requirement.
- **Env-only single operator (no table)** — smallest change, but no per-operator
  identity for audit/attribution and awkward for multiple operators.
- **External IdP (OAuth/OIDC)** — appropriate for production multi-tenant use, but
  disproportionate for the current simulated prototype.

## Consequences

- All operations-console endpoints now require a valid operator token; the IDOR
  surface flagged in the P2-A2 audit is closed behind authentication.
- A real identity now exists to attach future audit attribution and, if needed,
  role-based authorization.
- **Out of scope / future work:** per-operator audit attribution on conversations,
  role tiers (Tier-1 vs Tier-2 vs compliance), token revocation/refresh, rate
  limiting on `/auth/login`, and migration to an external IdP for production.
