"""Integration tests for the simulated customer verification flow (P2-A5)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VerificationChallengeModel


async def _create_tx(client: AsyncClient, amount: str, recipient: str = "Payee") -> str:
    res = await client.post(
        "/api/v1/transactions",
        json={
            "customer_id": "cust_verify",
            "idempotency_key": f"idemp_{uuid.uuid4().hex[:12]}",
            "amount": amount,
            "currency": "INR",
            "payment_rail": "IMPS",
            "recipient_name": recipient,
            "recipient_identifier": "payee@upi",
            "purpose": "Test",
        },
    )
    assert res.status_code == 201
    return res.json()["id"]


async def _drive_to_verification_required(client: AsyncClient) -> str:
    """Create a MEDIUM-tier transaction and run P2-A4 to VERIFICATION_REQUIRED."""
    tx_id = await _create_tx(client, "60000.00")
    res = await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={
            "evidence": {"is_first_time_recipient": True, "active_call_present": True},
            "run_investigation": False,
        },
    )
    assert res.status_code == 201
    assert res.json()["to_state"] == "VERIFICATION_REQUIRED"
    return tx_id


async def _create_challenge(client: AsyncClient, tx_id: str) -> dict:
    res = await client.post(f"/api/v1/transactions/{tx_id}/verification", json={})
    assert res.status_code in (200, 201)
    return res.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_eligible_transaction_creates_challenge(client: AsyncClient) -> None:
    tx_id = await _drive_to_verification_required(client)
    body = await _create_challenge(client, tx_id)
    assert body["status"] == "PENDING"
    assert body["max_attempts"] == 5
    assert body["attempts_remaining"] == 5
    assert body["simulated"] is True
    assert body["customer_session_token"]
    assert body["dev_otp"] and body["dev_otp"].isdigit()  # dev-only, enabled in tests


@pytest.mark.asyncio
async def test_challenge_not_created_when_not_required(client: AsyncClient) -> None:
    # Low-risk tx auto-settles; verification is not applicable.
    tx_id = await _create_tx(client, "15000.00")
    await client.post(
        f"/api/v1/transactions/{tx_id}/evaluate",
        json={"evidence": {"is_trusted_beneficiary": True}},
    )
    res = await client.post(f"/api/v1/transactions/{tx_id}/verification", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "VERIFICATION_NOT_REQUIRED"


@pytest.mark.asyncio
async def test_successful_verification_triggers_reevaluation_and_settles(
    client: AsyncClient,
) -> None:
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    res = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=_auth(ch["customer_session_token"]),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["result"] == "SUCCEEDED"
    # MEDIUM tier + verification satisfied -> ALLOW -> simulated settlement.
    assert body["decision"]["action"] == "ALLOW"
    assert body["transaction_state"] == "SETTLED_SIMULATED"
    assert body["decision"]["simulated"] is True
    assert "VERIFICATION_SATISFIED" in body["decision"]["reason_codes"]


@pytest.mark.asyncio
async def test_incorrect_otp_increments_attempts(client: AsyncClient) -> None:
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    res = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": "000000" if ch["dev_otp"] != "000000" else "111111"},
        headers=_auth(ch["customer_session_token"]),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["result"] == "FAILED"
    assert body["status"] == "PENDING"
    assert body["attempts_remaining"] == 4
    # Not settled.
    tx = (await client.get(f"/api/v1/transactions/{tx_id}")).json()
    assert tx["state"] == "VERIFICATION_REQUIRED"


@pytest.mark.asyncio
async def test_exhausted_attempts_hold_and_cannot_retry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    wrong = "000000" if ch["dev_otp"] != "000000" else "111111"
    headers = _auth(ch["customer_session_token"])
    last = None
    for _ in range(5):
        last = await client.post(
            f"/api/v1/verification/{ch['challenge_id']}/submit",
            json={"otp": wrong},
            headers=headers,
        )
    assert last is not None
    body = last.json()
    assert body["result"] == "EXHAUSTED"
    assert body["status"] == "FAILED"
    # Failed verification never settles: policy holds it.
    assert body["decision"]["action"] == "HOLD_FOR_INVESTIGATION"
    assert body["transaction_state"] == "HELD_FOR_VERIFICATION"

    # Even the correct OTP afterwards cannot succeed.
    retry = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=headers,
    )
    assert retry.status_code == 409


@pytest.mark.asyncio
async def test_expired_challenge_cannot_be_used(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    # Force expiry in the database.
    await db_session.execute(
        VerificationChallengeModel.__table__.update()
        .where(VerificationChallengeModel.id == uuid.UUID(ch["challenge_id"]))
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()

    res = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=_auth(ch["customer_session_token"]),
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VERIFICATION_EXPIRED"


@pytest.mark.asyncio
async def test_consumed_challenge_is_idempotent_not_reprocessed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    headers = _auth(ch["customer_session_token"])
    first = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=headers,
    )
    first_decision = first.json()["decision"]["id"]

    second = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["result"] == "SUCCEEDED"
    assert second.json()["decision"]["id"] == first_decision  # no new decision

    decisions = (
        await db_session.execute(
            select(VerificationChallengeModel).where(
                VerificationChallengeModel.id == uuid.UUID(ch["challenge_id"])
            )
        )
    ).scalar_one()
    assert decisions.status == "CONSUMED"


@pytest.mark.asyncio
async def test_challenge_cannot_be_used_across_transactions(client: AsyncClient) -> None:
    tx1 = await _drive_to_verification_required(client)
    ch1 = await _create_challenge(client, tx1)
    tx2 = await _drive_to_verification_required(client)
    ch2 = await _create_challenge(client, tx2)

    # Use ch1's session token against ch2's challenge path -> binding mismatch 404.
    res = await client.post(
        f"/api/v1/verification/{ch2['challenge_id']}/submit",
        json={"otp": ch1["dev_otp"]},
        headers=_auth(ch1["customer_session_token"]),
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_submit_requires_customer_session_token(
    client: AsyncClient, unauth_client: AsyncClient
) -> None:
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    # No token at all.
    res = await unauth_client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit", json={"otp": ch["dev_otp"]}
    )
    assert res.status_code == 401

    # A non-customer-verification token (here, an operator access token) is rejected.
    from app.core.security import create_access_token
    from tests.conftest import get_test_settings

    operator_token, _ = create_access_token(str(uuid.uuid4()), get_test_settings())
    res2 = await unauth_client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=_auth(operator_token),
    )
    assert res2.status_code == 401


@pytest.mark.asyncio
async def test_create_challenge_requires_operator_auth(unauth_client: AsyncClient) -> None:
    res = await unauth_client.post(f"/api/v1/transactions/{uuid.uuid4()}/verification", json={})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_terminal_transaction_cannot_be_reopened(client: AsyncClient) -> None:
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=_auth(ch["customer_session_token"]),
    )
    # Now SETTLED; a new challenge cannot be created.
    res = await client.post(f"/api/v1/transactions/{tx_id}/verification", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "VERIFICATION_NOT_REQUIRED"


@pytest.mark.asyncio
async def test_audit_and_decision_are_traceable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    submit = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=_auth(ch["customer_session_token"]),
    )
    decision_id = submit.json()["decision"]["id"]

    # The challenge links to the resulting decision.
    challenge = (
        await db_session.execute(
            select(VerificationChallengeModel).where(
                VerificationChallengeModel.id == uuid.UUID(ch["challenge_id"])
            )
        )
    ).scalar_one()
    assert str(challenge.decision_id) == decision_id

    # Audit trail shows the verification-driven transitions.
    audits = (await client.get(f"/api/v1/transactions/{tx_id}/audit")).json()["items"]
    states = [a["to_state"] for a in audits]
    assert "INVESTIGATING" in states
    assert states[-1] == "SETTLED_SIMULATED"


@pytest.mark.asyncio
async def test_status_endpoint_returns_challenge_state(client: AsyncClient) -> None:
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    res = await client.get(f"/api/v1/transactions/{tx_id}/verification/{ch['challenge_id']}")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "PENDING"
    assert body["transaction_state"] == "VERIFICATION_REQUIRED"


@pytest.mark.asyncio
async def test_concurrent_consumption_updates_are_single_use(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The optimistic version guard permits consuming a challenge at most once."""
    from app.repositories.transaction_repository import TransactionRepository

    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    repo = TransactionRepository(db_session)
    challenge = await repo.get_challenge_by_id(uuid.UUID(ch["challenge_id"]))
    assert challenge is not None
    version = challenge.version

    first = await repo.update_challenge_fields(challenge.id, version, {"status": "VERIFIED"})
    second = await repo.update_challenge_fields(challenge.id, version, {"status": "VERIFIED"})
    assert first is True
    assert second is False  # stale version -> cannot consume twice


@pytest.mark.asyncio
async def test_successful_verification_with_strong_residual_fraud_risk_remains_held(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verification is an additional signal and cannot bypass strong residual fraud risk."""
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)

    # Attach an investigation indicating coercion
    from app.db.models import TransactionInvestigationModel

    inv = TransactionInvestigationModel(
        id=uuid.uuid4(),
        transaction_id=uuid.UUID(tx_id),
        summary="Customer in active coercion situation under police duress",
        overall_risk_sentiment="COERCED",
        confidence="HIGH",
        confidence_score=0.95,
        findings=[
            {
                "id": "f_coercion",
                "category": "AUTHORITY_COERCION",
                "explanation": "Active caller claiming to be police",
                "severity": "CRITICAL",
                "supporting_evidence_references": ["stmt_1"],
                "source_provenance": "customer_statement",
            }
        ],
        missing_information=[],
        unresolved_questions=[],
        suggested_next_steps=[],
        contradictory_evidence=[],
        model_metadata={"provider": "mock"},
        input_snapshot={},
    )
    db_session.add(inv)
    await db_session.commit()

    # Submit correct OTP
    res = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=_auth(ch["customer_session_token"]),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["result"] == "SUCCEEDED"
    # Even though verification succeeded, strong residual risk forces HOLD!
    assert body["decision"]["action"] == "HOLD_FOR_INVESTIGATION"
    assert body["transaction_state"] == "HELD_FOR_VERIFICATION"
    assert "VERIFICATION_INSUFFICIENT_RESIDUAL_RISK" in body["decision"]["reason_codes"]


@pytest.mark.asyncio
async def test_concurrent_correct_submissions_safe_resolution(client: AsyncClient) -> None:
    """SEC-02: Concurrent submissions resolve safely and never claim success before decision."""
    import asyncio

    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    headers = _auth(ch["customer_session_token"])
    payload = {"otp": ch["dev_otp"]}
    url = f"/api/v1/verification/{ch['challenge_id']}/submit"

    res1, res2 = await asyncio.gather(
        client.post(url, json=payload, headers=headers),
        client.post(url, json=payload, headers=headers),
    )

    # Both requests must complete cleanly without 500 errors.
    assert res1.status_code in (200, 409)
    assert res2.status_code in (200, 409)

    # At least one request won and returned 200 with decision.
    successes = [r for r in (res1, res2) if r.status_code == 200]
    assert len(successes) >= 1
    winner = successes[0].json()
    assert winner["result"] == "SUCCEEDED"
    assert winner["decision"] is not None
    assert winner["decision"]["action"] == "ALLOW"
    assert winner["transaction_state"] == "SETTLED_SIMULATED"


@pytest.mark.asyncio
async def test_concurrent_racing_correct_and_incorrect_no_missing_greenlet(
    client: AsyncClient,
) -> None:
    """SEC-01: Correct racing incorrect does not crash with MissingGreenlet."""
    import asyncio

    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)
    headers = _auth(ch["customer_session_token"])
    wrong_otp = "000000" if ch["dev_otp"] != "000000" else "111111"
    url = f"/api/v1/verification/{ch['challenge_id']}/submit"

    res_correct, res_incorrect = await asyncio.gather(
        client.post(url, json={"otp": ch["dev_otp"]}, headers=headers),
        client.post(url, json={"otp": wrong_otp}, headers=headers),
    )

    # Neither request should return 500 Internal Server Error
    assert res_correct.status_code in (200, 409)
    assert res_incorrect.status_code == 200

    # The transaction must be in a consistent state (either resolved or held)
    tx = (await client.get(f"/api/v1/transactions/{tx_id}")).json()
    assert tx["state"] in ("SETTLED_SIMULATED", "VERIFICATION_REQUIRED", "HELD_FOR_VERIFICATION")


@pytest.mark.asyncio
async def test_duplicate_concurrent_challenge_creation_handled_gracefully(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SEC-03: Concurrent creation resolves via partial unique index without duplicates."""
    import asyncio

    tx_id = await _drive_to_verification_required(client)

    res1, res2 = await asyncio.gather(
        client.post(f"/api/v1/transactions/{tx_id}/verification", json={}),
        client.post(f"/api/v1/transactions/{tx_id}/verification", json={}),
    )

    assert res1.status_code in (200, 201)
    assert res2.status_code in (200, 201)

    # Exactly one challenge ID is active for this transaction
    ch1_id = res1.json()["challenge_id"]
    ch2_id = res2.json()["challenge_id"]
    assert ch1_id == ch2_id

    # Verify database has at most 1 PENDING challenge for this transaction
    pending_challenges = (
        (
            await db_session.execute(
                select(VerificationChallengeModel).where(
                    VerificationChallengeModel.transaction_id == uuid.UUID(tx_id),
                    VerificationChallengeModel.status == "PENDING",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(pending_challenges) == 1


@pytest.mark.asyncio
async def test_submission_rejected_when_transaction_in_terminal_state(
    client: AsyncClient,
) -> None:
    """SEC-04: Submission on cancelled transaction fails safely."""
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)

    # Cancel transaction
    cancel_res = await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={
            "target_state": "CANCELLED_SIMULATED",
            "actor_type": "CUSTOMER",
            "reason": "Customer cancelled during verification",
        },
    )
    assert cancel_res.status_code == 200

    # Submit OTP -> must reject with TRANSACTION_TERMINAL (409)
    res = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=_auth(ch["customer_session_token"]),
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "TRANSACTION_TERMINAL"


@pytest.mark.asyncio
async def test_submission_rejected_when_transaction_not_verification_required(
    client: AsyncClient,
) -> None:
    """SEC-04: Submission when transaction moved to HUMAN_REVIEW rejects before verifying."""
    tx_id = await _drive_to_verification_required(client)
    ch = await _create_challenge(client, tx_id)

    # Operator transitions to INVESTIGATING then HUMAN_REVIEW
    await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={"target_state": "INVESTIGATING", "actor_type": "CUSTOMER", "reason": "investigating"},
    )
    await client.post(
        f"/api/v1/transactions/{tx_id}/transitions",
        json={
            "target_state": "HUMAN_REVIEW",
            "actor_type": "INVESTIGATOR",
            "reason": "operator escalation",
        },
    )

    # Submit OTP -> must reject with VERIFICATION_NOT_REQUIRED (409)
    res = await client.post(
        f"/api/v1/verification/{ch['challenge_id']}/submit",
        json={"otp": ch["dev_otp"]},
        headers=_auth(ch["customer_session_token"]),
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "VERIFICATION_NOT_REQUIRED"


@pytest.mark.asyncio
async def test_hmac_secret_key_rotation_dual_verification() -> None:
    """SEC-05: verify_otp supports key rotation using fallback secret for legacy challenges."""
    from app.core.config import Settings
    from app.core.security import hash_otp, verify_otp

    # 1. Challenge was hashed under initial secret (e.g. AUTH_JWT_SECRET)
    initial_settings = Settings(
        AUTH_JWT_SECRET="old-legacy-jwt-secret-string-32bytes",
        VERIFICATION_HMAC_SECRET=None,
    )
    otp = "654321"
    digest = hash_otp(otp, initial_settings)

    # 2. Key is rotated: new dedicated VERIFICATION_HMAC_SECRET is deployed
    rotated_settings = Settings(
        AUTH_JWT_SECRET="old-legacy-jwt-secret-string-32bytes",
        VERIFICATION_HMAC_SECRET="new-dedicated-hmac-secret-string",
    )

    # Existing digest matches via dual-key fallback rotation!
    assert verify_otp(otp, digest, rotated_settings) is True

    # New digest hashed with new dedicated secret also matches
    new_digest = hash_otp(otp, rotated_settings)
    assert verify_otp(otp, new_digest, rotated_settings) is True

    # Wrong OTP still fails
    assert verify_otp("000000", digest, rotated_settings) is False


@pytest.mark.asyncio
async def test_challenge_creation_abuse_rate_limit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SEC-06: Database-backed rate limit bounds repeated challenge creation abuse."""
    from app.core.config import get_settings

    settings = get_settings()
    tx_id = await _drive_to_verification_required(client)

    # Rapidly create challenges by forcing expiry on each so a new one is requested
    limit = settings.VERIFICATION_MAX_CHALLENGES_PER_WINDOW
    for _i in range(limit):
        ch = await _create_challenge(client, tx_id)
        # Force expiry in DB so the next call attempts to create a new challenge
        await db_session.execute(
            VerificationChallengeModel.__table__.update()
            .where(VerificationChallengeModel.id == uuid.UUID(ch["challenge_id"]))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db_session.commit()

    # The next attempt must be rejected by database-backed rate limit (429)
    res = await client.post(f"/api/v1/transactions/{tx_id}/verification", json={})
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
