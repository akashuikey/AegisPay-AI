"""Integration tests for AI forensic investigations API endpoints.
Tests persistence in PostgreSQL, schema serialization, dependency overrides,
and state machine non-mutation invariants.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.investigations import get_default_ai_client
from app.core.errors import AIProviderError
from app.db.models import (
    InvestigationConversationTurnModel,
    TransactionAuditModel,
    TransactionInvestigationModel,
)
from app.domain.investigation import (
    ConfidenceLevel,
    EvidenceProvenance,
    FindingCategory,
    InvestigationModelMetadata,
    RiskSentiment,
)
from app.schemas.investigation import (
    InvestigationFindingSchema,
    InvestigationStructuredOutput,
)
from app.services.ai_client import MockGeminiClient


@pytest.mark.asyncio
async def test_create_and_retrieve_investigation_lifecycle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify end-to-end investigation creation, persistence, and retrieval."""
    # 1. Create a simulated transaction
    tx_payload = {
        "customer_id": "cust_inv_test_01",
        "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
        "amount": "250000.00",
        "currency": "INR",
        "payment_rail": "RTGS",
        "recipient_name": "Govt Security Clearance Account",
        "recipient_identifier": "cbi.clearance@sbi",
        "purpose": "Urgent court identity bond",
    }
    tx_res = await client.post("/api/v1/transactions", json=tx_payload)
    assert tx_res.status_code == 201
    tx_data = tx_res.json()
    tx_id = tx_data["id"]

    # 2. Perform deterministic risk assessment
    assess_res = await client.post(
        f"/api/v1/transactions/{tx_id}/assess",
        json={
            "evidence": {
                "amount": 250000.0,
                "is_first_time_recipient": True,
                "recent_fd_liquidation": True,
                "active_call_present": True,
                "screen_sharing_active": True,
                "coercive_language_detected": True,
            }
        },
    )
    assert assess_res.status_code == 200
    assess_id = assess_res.json()["id"]

    # Record transaction state before AI investigation
    tx_before_res = await client.get(f"/api/v1/transactions/{tx_id}")
    tx_before = tx_before_res.json()

    # 3. Request AI investigation
    inv_payload = {
        "transaction_id": tx_id,
        "assessment_id": assess_id,
        "customer_statements": [
            {
                "statement_id": "stmt_01",
                "question": "Why are you making this transfer?",
                "answer": (
                    "Officer Verma from CBI said I must transfer ₹2,50,000 immediately "
                    "or I will be arrested."
                ),
                "channel": "chat",
            }
        ],
        "document_extractions": [
            {
                "doc_id": "doc_warrant_01",
                "document_type": "ARREST_WARRANT",
                "claimed_issuer": "Supreme Court / CBI Cyber Division",
                "claimed_amount": 250000.0,
                "extracted_text": (
                    "Non-bailable warrant issued. Clear payment to security account "
                    "to avoid custody."
                ),
                "verification_source": "whatsapp_download",
            }
        ],
        "telephony_telemetry": {
            "active_call_present": True,
            "screen_sharing_active": True,
            "voice_stress_detected": True,
            "call_duration_seconds": 1820,
        },
        "recipient_intelligence": {
            "is_flagged_mule": False,
            "account_age_days": 12,
            "fan_in_count_24h": 3,
            "fan_out_count_24h": 2,
        },
        "coercion_cues": ["legal intimidation", "immediate arrest threat", "secrecy demand"],
        "correlation_id": "corr_integ_test_01",
    }

    inv_res = await client.post("/api/v1/investigations", json=inv_payload)
    assert inv_res.status_code == 201

    inv_data = inv_res.json()
    assert "id" in inv_data
    investigation_id = inv_data["id"]
    assert inv_data["transaction_id"] == tx_id
    assert inv_data["assessment_id"] == assess_id
    assert inv_data["overall_risk_sentiment"] in ("COERCED", "SUSPICIOUS")
    assert inv_data["confidence"] in ("HIGH", "MEDIUM")
    assert isinstance(inv_data["confidence_score"], float)
    assert len(inv_data["findings"]) > 0
    assert inv_data["model_metadata"]["provider"] == "mock_gemini"

    # 4. Verify record in PostgreSQL database
    stmt = select(TransactionInvestigationModel).where(
        TransactionInvestigationModel.id == uuid.UUID(investigation_id)
    )
    db_record = (await db_session.execute(stmt)).scalar_one_or_none()
    assert db_record is not None
    assert str(db_record.transaction_id) == tx_id
    assert db_record.overall_risk_sentiment == inv_data["overall_risk_sentiment"]

    # 5. Fetch single investigation by ID
    get_res = await client.get(f"/api/v1/investigations/{investigation_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == investigation_id

    # 6. Fetch investigations list for transaction
    list_res = await client.get(f"/api/v1/transactions/{tx_id}/investigations")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["transaction_id"] == tx_id
    assert list_data["total_entries"] >= 1
    assert any(item["id"] == investigation_id for item in list_data["items"])

    # 7. CRITICAL STATE INVARIANT: Verify transaction state was NOT modified
    tx_after_res = await client.get(f"/api/v1/transactions/{tx_id}")
    tx_after = tx_after_res.json()
    assert tx_after["state"] == tx_before["state"]
    assert tx_after["version"] == tx_before["version"]


@pytest.mark.asyncio
async def test_investigation_nonexistent_transaction_returns_404(client: AsyncClient) -> None:
    """Verify investigating a nonexistent transaction returns 404."""
    random_id = str(uuid.uuid4())
    payload = {
        "transaction_id": random_id,
        "customer_statements": [],
    }
    response = await client.post("/api/v1/investigations", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_nonexistent_investigation_returns_404(client: AsyncClient) -> None:
    """Verify fetching nonexistent investigation ID returns 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/investigations/{random_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_list_investigations_nonexistent_transaction_returns_404(
    client: AsyncClient,
) -> None:
    """Verify listing investigations for nonexistent transaction returns 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/transactions/{random_id}/investigations")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_investigation_provider_failure_returns_502(client: AsyncClient) -> None:
    """Verify that an AI provider failure returns HTTP 502 with structured error envelope."""
    # 1. Create a transaction
    tx_res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_fail_01",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": "10000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Test Payee",
            "recipient_identifier": "payee@upi",
            "purpose": "Test",
        },
    )
    assert tx_res.status_code == 201
    tx_id = tx_res.json()["id"]

    # 2. Inject failing AI client override
    app = client._transport.app  # type: ignore[attr-defined]
    failing_client = MockGeminiClient(should_fail=True)
    app.dependency_overrides[get_default_ai_client] = lambda: failing_client

    try:
        response = await client.post(
            "/api/v1/investigations",
            json={"transaction_id": tx_id},
        )
        assert response.status_code == 502
        data = response.json()
        assert data["error"]["code"] == "AI_PROVIDER_ERROR"
    finally:
        # Restore default mock client
        app.dependency_overrides[get_default_ai_client] = lambda: MockGeminiClient()


@pytest.mark.asyncio
async def test_investigation_provider_permission_denied_returns_502(client: AsyncClient) -> None:
    """Verify HTTP 403 provider permission denied returns HTTP 502 with AI_PERMISSION_DENIED."""
    tx_res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_perm_01",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": "10000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Test Payee",
            "recipient_identifier": "payee@upi",
            "purpose": "Test",
        },
    )
    assert tx_res.status_code == 201
    tx_id = tx_res.json()["id"]

    app = client._transport.app  # type: ignore[attr-defined]
    perm_denied_client = MockGeminiClient(
        should_fail=True,
        failure_exception=AIProviderError(
            message="AI investigation permission denied or authentication failure with provider",
            code="AI_PERMISSION_DENIED",
            status_code=502,
        ),
    )
    app.dependency_overrides[get_default_ai_client] = lambda: perm_denied_client

    try:
        response = await client.post(
            "/api/v1/investigations",
            json={"transaction_id": tx_id},
        )
        assert response.status_code == 502
        data = response.json()
        assert data["error"]["code"] == "AI_PERMISSION_DENIED"
    finally:
        app.dependency_overrides[get_default_ai_client] = lambda: MockGeminiClient()


@pytest.mark.asyncio
async def test_investigation_failure_preserves_transaction_state_and_audit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """CRITICAL ISOLATION TEST:
    Verify that an AI investigation failure leaves transaction state, version,
    and audit log entries completely unchanged.
    """
    # 1. Create a transaction
    tx_res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_iso_01",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": "80000.00",
            "currency": "INR",
            "payment_rail": "IMPS",
            "recipient_name": "Test Beneficiary",
            "recipient_identifier": "beneficiary@upi",
            "purpose": "Rent",
        },
    )
    assert tx_res.status_code == 201
    tx_id = tx_res.json()["id"]

    # 2. Query initial audit count and transaction snapshot
    tx_before = (await client.get(f"/api/v1/transactions/{tx_id}")).json()
    audit_stmt = select(TransactionAuditModel).where(
        TransactionAuditModel.transaction_id == uuid.UUID(tx_id)
    )
    audits_before = (await db_session.execute(audit_stmt)).scalars().all()
    audit_count_before = len(audits_before)

    # 3. Inject failing AI client
    app = client._transport.app  # type: ignore[attr-defined]
    failing_client = MockGeminiClient(should_fail=True)
    app.dependency_overrides[get_default_ai_client] = lambda: failing_client

    try:
        response = await client.post(
            "/api/v1/investigations",
            json={"transaction_id": tx_id},
        )
        assert response.status_code == 502
    finally:
        app.dependency_overrides[get_default_ai_client] = lambda: MockGeminiClient()

    # 4. Invariant: Transaction state, version, and audits are strictly unchanged
    tx_after = (await client.get(f"/api/v1/transactions/{tx_id}")).json()
    assert tx_after["state"] == tx_before["state"]
    assert tx_after["version"] == tx_before["version"]

    audits_after = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(audits_after) == audit_count_before


@pytest.mark.asyncio
async def test_investigation_evidence_integrity_end_to_end(client: AsyncClient) -> None:
    """Verify end-to-end that fabricated evidence references are scrubbed and tracked."""
    tx_res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_integ_e2e_01",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": "45000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Tech Corp",
            "recipient_identifier": "tech@upi",
            "purpose": "Hardware invoice",
        },
    )
    assert tx_res.status_code == 201
    tx_id = tx_res.json()["id"]

    # Mock client that produces a mix of valid and fabricated evidence references
    class HallucinatingAIClient:
        async def generate_investigation(
            self, prompt: str, system_instruction: str, correlation_id: str | None = None
        ) -> tuple[InvestigationStructuredOutput, InvestigationModelMetadata]:
            output = InvestigationStructuredOutput(
                summary="Analysis with fabricated citations.",
                overall_risk_sentiment=RiskSentiment.SUSPICIOUS,
                confidence=ConfidenceLevel.MEDIUM,
                confidence_score=0.72,
                findings=[
                    InvestigationFindingSchema(
                        id="FINDING-CITATIONS",
                        category=FindingCategory.BENEFICIARY_INCONSISTENCY,
                        explanation="Inconsistent invoice details noted.",
                        severity="MEDIUM",
                        supporting_evidence_references=[
                            "stmt_legit_01",
                            "stmt_hallucinated_888",
                            "doc_unsupplied_fbi",
                        ],
                        source_provenance=EvidenceProvenance.CUSTOMER_STATEMENT,
                    )
                ],
                contradictory_or_mitigating_evidence=[],
                missing_information=[],
                unresolved_questions=[],
                suggested_next_steps=[],
            )
            metadata = InvestigationModelMetadata(
                provider="mock_gemini",
                model_id="gemini-2.5-flash",
                latency_ms=12.0,
                correlation_id=correlation_id,
            )
            return output, metadata

    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_default_ai_client] = lambda: HallucinatingAIClient()

    try:
        response = await client.post(
            "/api/v1/investigations",
            json={
                "transaction_id": tx_id,
                "customer_statements": [
                    {
                        "statement_id": "stmt_legit_01",
                        "question": "Is this invoice valid?",
                        "answer": "Yes, I verified the bank details.",
                    }
                ],
            },
        )
        assert response.status_code == 201
        data = response.json()

        finding = data["findings"][0]
        # Valid reference retained
        assert "stmt_legit_01" in finding["supporting_evidence_references"]
        # Fabricated references scrubbed
        assert "stmt_hallucinated_888" not in finding["supporting_evidence_references"]
        assert "doc_unsupplied_fbi" not in finding["supporting_evidence_references"]

        # Missing information captures the rejection
        assert any("stmt_hallucinated_888" in msg for msg in data["missing_information"])
        assert any("doc_unsupplied_fbi" in msg for msg in data["missing_information"])
    finally:
        app.dependency_overrides[get_default_ai_client] = lambda: MockGeminiClient()


# ---------------------------------------------------------------------------
# Investigation Conversation End-to-End Integration Tests (P2-A2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conversation_api_lifecycle(client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify multi-turn investigation session creation, turns, and non-mutation."""
    # 1. Create transaction
    tx_res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_multi_turn_01",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": "450000.00",
            "currency": "INR",
            "payment_rail": "IMPS",
            "recipient_name": "Cyber Police Reserve Account",
            "recipient_identifier": "cyber.cbi@hdfc",
            "purpose": "Digital arrest clearance bond",
        },
    )
    assert tx_res.status_code == 201
    tx_data = tx_res.json()
    tx_id = tx_data["id"]
    initial_version = tx_data["version"]
    initial_state = tx_data["state"]

    # 2. Start investigation conversation without initial message
    conv_start_res = await client.post(
        f"/api/v1/transactions/{tx_id}/conversations",
        json={},
    )
    assert conv_start_res.status_code == 201
    conv_data = conv_start_res.json()
    conv_id = conv_data["id"]
    assert conv_data["transaction_id"] == tx_id
    assert conv_data["turn_count"] == 1
    assert len(conv_data["turns"]) == 1
    assert conv_data["turns"][0]["role"] == "assistant"
    assert len(conv_data["turns"][0]["follow_up_questions"]) > 0

    # 3. Submit operator turn with customer answer
    turn_res = await client.post(
        f"/api/v1/conversations/{conv_id}/turns",
        json={
            "content": (
                "Customer states caller claimed to be CBI Officer Sharma. Customer was ordered "
                "not to disconnect under threat of immediate non-bailable arrest."
            ),
            "evidence_provenance": "customer_statement",
        },
    )
    assert turn_res.status_code == 201
    updated_conv = turn_res.json()
    assert updated_conv["turn_count"] == 3
    turns = updated_conv["turns"]
    assert turns[1]["role"] == "operator"
    assert turns[2]["role"] == "assistant"
    assert turns[2]["risk_sentiment"] == "COERCED"
    assert any(f["id"] == "FINDING-COERCION" for f in turns[2]["findings"])

    # 4. Fetch current conversation for transaction
    current_res = await client.get(f"/api/v1/transactions/{tx_id}/conversations/current")
    assert current_res.status_code == 200
    assert current_res.json()["id"] == conv_id

    # 5. List conversations for transaction
    list_res = await client.get(f"/api/v1/transactions/{tx_id}/conversations")
    assert list_res.status_code == 200
    assert list_res.json()["total_entries"] == 1

    # 6. Fetch conversation by primary ID
    conv_by_id_res = await client.get(f"/api/v1/conversations/{conv_id}")
    assert conv_by_id_res.status_code == 200
    assert conv_by_id_res.json()["id"] == conv_id

    # 7. Non-Mutation Invariant: Verify transaction state and version were NOT mutated
    tx_check_res = await client.get(f"/api/v1/transactions/{tx_id}")
    assert tx_check_res.status_code == 200
    tx_after = tx_check_res.json()
    assert tx_after["state"] == initial_state
    assert tx_after["version"] == initial_version

    # Verify no audit records were created by the conversation
    audits_res = await client.get(f"/api/v1/transactions/{tx_id}/audit")
    assert audits_res.status_code == 200
    # Exactly 1 audit record from initial transaction creation
    assert audits_res.json()["total_entries"] == 1


@pytest.mark.asyncio
async def test_conversation_api_cross_transaction_isolation(client: AsyncClient) -> None:
    """Verify cross-transaction scoping enforces 404 on mismatched transaction ID."""
    # Create tx1 and start conversation
    tx1_res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_iso_1",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": "10000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Merchant 1",
            "recipient_identifier": "m1@upi",
            "purpose": "Groceries",
        },
    )
    tx1_id = tx1_res.json()["id"]
    conv_res = await client.post(f"/api/v1/transactions/{tx1_id}/conversations", json={})
    conv_id = conv_res.json()["id"]

    # Create tx2
    tx2_res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_iso_2",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": "20000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Merchant 2",
            "recipient_identifier": "m2@upi",
            "purpose": "Electronics",
        },
    )
    tx2_id = tx2_res.json()["id"]

    # Attempt to submit turn for conv1 through tx2 URL
    mismatch_res = await client.post(
        f"/api/v1/transactions/{tx2_id}/conversations/{conv_id}/turns",
        json={"content": "Attempting cross-transaction conversation injection"},
    )
    assert mismatch_res.status_code == 404
    assert "not found" in mismatch_res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_conversation_turn_client_turn_id_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify a retried turn carrying the same client_turn_id does not create duplicate turns.

    Regression: the client_turn_id field is documented as an idempotency token to prevent
    accidental duplicate submission. Submitting the same token twice must be a no-op replay
    returning the existing conversation state rather than appending a second operator/assistant
    turn pair.
    """
    tx_res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_idem_turn_01",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": "50000.00",
            "currency": "INR",
            "payment_rail": "UPI",
            "recipient_name": "Payee",
            "recipient_identifier": "p@upi",
            "purpose": "Test",
        },
    )
    assert tx_res.status_code == 201
    tx_id = tx_res.json()["id"]

    conv_res = await client.post(f"/api/v1/transactions/{tx_id}/conversations", json={})
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]
    assert conv_res.json()["turn_count"] == 1

    token = "client-token-abc-123"
    body = {
        "content": "Customer states caller claimed to be CBI Officer Sharma.",
        "client_turn_id": token,
    }

    first = await client.post(f"/api/v1/conversations/{conv_id}/turns", json=body)
    assert first.status_code == 201
    first_data = first.json()
    assert first_data["turn_count"] == 3

    # Retry the same logical submission (same client_turn_id) -> idempotent no-op replay
    retry = await client.post(f"/api/v1/conversations/{conv_id}/turns", json=body)
    assert retry.status_code == 201
    retry_data = retry.json()
    assert retry_data["turn_count"] == 3, "retry must not create duplicate turns"
    assert len(retry_data["turns"]) == 3

    # A genuinely new submission (no token / different token) still appends turns
    new_body = {"content": "Follow-up: customer confirms active call ongoing."}
    third = await client.post(f"/api/v1/conversations/{conv_id}/turns", json=new_body)
    assert third.status_code == 201
    assert third.json()["turn_count"] == 5

    # Confirm persistence: only one operator turn carries the idempotency token
    turn_stmt = select(InvestigationConversationTurnModel).where(
        InvestigationConversationTurnModel.conversation_id == uuid.UUID(conv_id)
    )
    turns = (await db_session.execute(turn_stmt)).scalars().all()
    tokened = [t for t in turns if (t.model_metadata or {}).get("client_turn_id") == token]
    assert len(tokened) == 1
