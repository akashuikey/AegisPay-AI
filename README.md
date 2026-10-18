# AegisPay AI - Fraud & Coercion Prevention Platform

**AegisPay AI** is a real-time banking fraud and coercion prevention platform. It safeguards authorized push payments (APP) and instant transfers through pre-authorization risk scoring, deterministic decision policies, and contextual multi-modal investigations.

> [!IMPORTANT]
> **Safety & Simulation Guardrail**:
> All payment rails, accounts, UPI/NPCI interfaces, identity registries, and external messaging channels are **strictly simulated**. AegisPay AI does not connect to real financial networks, real customer bank accounts, or external payment gateways.

---

## 1. Overview & Core Features

AegisPay AI provides a complete operations console and simulation lab built in React & TypeScript:

- **Pre-Authorization Deterministic Risk Engine**: 11-rule automated scoring model assessing amounts, FD liquidation, remote screen sharing, authority coercion language, mule accounts, velocity, and trusted beneficiaries.
- **Scenario Simulation Lab (P2-A8)**: End-to-end execution of the 6 authoritative demo fraud scenarios (Digital Arrest, High-Yield Investment Scam, Fake Invoice Mismatch, Mule Network Dispersal, Legitimate Lease Payment, Ambiguous Payment). Inspect the evidence-to-decision-to-intervention timeline and compare observed outcomes against expectations.
- **Interactive Customer Call & Dialogue Simulator**: Real-time multi-turn voice and text dialogue simulating outbound bank welfare calls, interactive questions, turn tracking, and terminal protection actions.
- **Voice Duress & Coercion Intelligence (P2-A6)**: Transcript analysis detecting authority impersonation, arrest threats, secrecy demands, and acoustic voice stress signals.
- **Customer Verification Lifecycle (P2-A5)**: Outbound 2FA OTP challenges with dev OTP inspection, attempt counters, and state transitions.
- **Automated Fraud Response & Customer Intervention (P2-A7)**: Policy-authorized protective holds, account safety interventions, and simulated multi-channel notifications (In-App, SMS, WhatsApp, Email).
- **Multi-Modal AI Investigation & Review (P2-A2/A3)**: Forensic inquiry summaries, evidence provenance tracking, and operator case notes.
- **Operator Authentication (ADR-002)**: Role-gated access with session token lifecycle and operator identity tracking.

---

## 2. Getting Started

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

The application runs on `http://0.0.0.0:3000`.

### Production Build

```bash
npm run build
npm run preview
```

---

## 3. Demo Walkthrough

1. Open the app — the operator session automatically connects with bootstrap operator credentials (`operator` / `aegispass`).
2. Explore **Live Payments** to review incoming transactions, trigger risk assessments, or initiate an interactive outbound call to the simulated customer phone on the right.
3. Open **Scenario Lab** to run any of the 6 canonical scenarios (e.g. *1. Digital Arrest / Authority Impersonation* or *5. Legitimate High-Value Lease Payment*) and view the real-time stage execution timeline and 4-dimension evaluation report.
4. Test **Verification Challenges** with the displayed Dev OTP or enter deliberate mismatches to observe security exhaustion transitions.
5. Review **Verification Sources** for consortium mule registries and vendor ledger mismatches.
