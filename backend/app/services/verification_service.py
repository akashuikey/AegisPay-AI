"""Simulated customer verification challenge service (P2-A5).

Issues a SIMULATED OTP challenge for a verification-required transaction, binds
it to a distinct customer verification session, validates submissions securely
(keyed digest, expiry, bounded attempts, single-use consumption under
concurrency), and triggers deterministic policy re-evaluation. Verification is
an additional signal; it never settles a transaction on its own and never
overrides strong fraud evidence.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import VerificationError
from app.core.logging import get_logger
from app.core.security import (
    create_customer_verification_token,
    generate_otp,
    hash_otp,
    verify_otp,
)
from app.db.models import TransactionDecisionModel, VerificationChallengeModel
from app.domain.decision_policy import VerificationOutcome
from app.domain.state_machine import TransactionState
from app.repositories.transaction_repository import TransactionRepository
from app.services.decision_workflow_service import DecisionWorkflowService
from app.services.transaction_service import TransactionService

logger = get_logger(__name__)


class VerificationSubmitResult:
    """Lightweight container for a submission outcome returned to the API layer."""

    def __init__(
        self,
        challenge: VerificationChallengeModel,
        result: VerificationOutcome,
        transaction_state: str,
        decision: TransactionDecisionModel | None,
    ) -> None:
        self.challenge = challenge
        self.result = result
        self.transaction_state = transaction_state
        self.decision = decision


class VerificationService:
    """Coordinates the simulated customer verification challenge lifecycle."""

    def __init__(
        self,
        repository: TransactionRepository,
        transaction_service: TransactionService,
        workflow_service: DecisionWorkflowService,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.transaction_service = transaction_service
        self.workflow_service = workflow_service
        self.settings = settings

    async def create_or_get_challenge(
        self, transaction_id: UUID
    ) -> tuple[VerificationChallengeModel, str | None, str, int]:
        """Create a challenge (or return the active one) for a verification-required tx.

        Returns (challenge, dev_otp_or_none, session_token, session_expires_in).
        """
        tx = await self.transaction_service.get_transaction(transaction_id)
        if tx.state != TransactionState.VERIFICATION_REQUIRED.value:
            raise VerificationError(
                "Transaction does not currently require verification",
                code="VERIFICATION_NOT_REQUIRED",
                status_code=409,
            )
        customer_id = tx.customer_id

        # Abuse controls (SEC-06): bounded database-enforced window limits on challenge creation.
        recent_count = await self.repository.count_recent_challenges_for_transaction(
            transaction_id, self.settings.VERIFICATION_CHALLENGE_WINDOW_SECONDS
        )
        if recent_count >= self.settings.VERIFICATION_MAX_CHALLENGES_PER_WINDOW:
            max_ch = self.settings.VERIFICATION_MAX_CHALLENGES_PER_WINDOW
            win_min = self.settings.VERIFICATION_CHALLENGE_WINDOW_SECONDS // 60
            raise VerificationError(
                f"Rate limit exceeded: maximum {max_ch} challenges per {win_min} minutes",
                code="RATE_LIMIT_EXCEEDED",
                status_code=429,
            )

        existing = await self.repository.get_latest_pending_challenge(transaction_id)
        now = datetime.now(UTC)
        if existing is not None:
            if existing.expires_at > now:
                # Active challenge exists: return it (OTP is not re-displayed — not stored).
                token, expires_in = create_customer_verification_token(
                    challenge_id=str(existing.id),
                    transaction_id=str(transaction_id),
                    customer_id=customer_id,
                    settings=self.settings,
                )
                return existing, None, token, expires_in
            # Expired: mark it so a fresh challenge can be issued.
            cid = existing.id
            cver = existing.version
            await self.repository.update_challenge_fields(cid, cver, {"status": "EXPIRED"})

        otp = generate_otp(self.settings.VERIFICATION_OTP_LENGTH)
        challenge = VerificationChallengeModel(
            id=uuid4(),
            transaction_id=transaction_id,
            customer_id=customer_id,
            otp_digest=hash_otp(otp, self.settings),
            status="PENDING",
            attempt_count=0,
            max_attempts=self.settings.VERIFICATION_MAX_ATTEMPTS,
            version=1,
            expires_at=now + timedelta(seconds=self.settings.VERIFICATION_CHALLENGE_TTL_SECONDS),
        )
        try:
            saved = await self.repository.create_challenge(challenge)
        except IntegrityError:
            # Concurrent creation race (SEC-03): another worker inserted a pending challenge.
            # Handle gracefully by loading the winning pending challenge.
            existing = await self.repository.get_latest_pending_challenge(transaction_id)
            if existing is not None:
                token, expires_in = create_customer_verification_token(
                    challenge_id=str(existing.id),
                    transaction_id=str(transaction_id),
                    customer_id=customer_id,
                    settings=self.settings,
                )
                return existing, None, token, expires_in
            raise

        token, expires_in = create_customer_verification_token(
            challenge_id=str(saved.id),
            transaction_id=str(transaction_id),
            customer_id=customer_id,
            settings=self.settings,
        )
        dev_otp = otp if self.settings.VERIFICATION_EXPOSE_DEV_OTP else None
        logger.info(
            "Created simulated verification challenge %s for tx=%s (expose_dev_otp=%s)",
            saved.id,
            transaction_id,
            self.settings.VERIFICATION_EXPOSE_DEV_OTP,
        )
        return saved, dev_otp, token, expires_in

    async def get_status(
        self, transaction_id: UUID, challenge_id: UUID
    ) -> VerificationChallengeModel:
        """Fetch a challenge, enforcing transaction binding."""
        challenge = await self._load_bound_challenge(transaction_id, challenge_id)
        return challenge

    async def submit(
        self,
        *,
        challenge_id: UUID,
        transaction_id: UUID,
        customer_id: UUID | str,
        otp: str,
    ) -> VerificationSubmitResult:
        """Validate a verification submission and, on resolution, re-evaluate policy."""
        challenge = await self._load_bound_challenge(transaction_id, challenge_id)
        cid = challenge.id

        if challenge.customer_id != str(customer_id):
            # Session/customer binding mismatch -> generic 404-style rejection.
            raise VerificationError(
                "Verification challenge not found for this session",
                code="VERIFICATION_CHALLENGE_INVALID",
                status_code=404,
            )

        # 1. Idempotent success replay: already resolved with a decision.
        if challenge.status in ("VERIFIED", "CONSUMED") and challenge.decision_id is not None:
            decision = await self.repository.get_latest_decision_for_transaction(transaction_id)
            tx = await self.transaction_service.get_transaction(transaction_id)
            return VerificationSubmitResult(
                challenge, VerificationOutcome.SUCCEEDED, tx.state, decision
            )

        # 2. In-flight race window (SEC-02): winning request claimed lock (VERIFIED) but decision
        # persistence is in progress. Wait up to 3.0s (polling every 100ms) for resolution.
        if challenge.status == "VERIFIED" and challenge.decision_id is None:
            for _ in range(30):
                await asyncio.sleep(0.1)
                refreshed = await self.repository.get_challenge_by_id(cid)
                if refreshed is not None and refreshed.decision_id is not None:
                    decision = await self.repository.get_latest_decision_for_transaction(
                        transaction_id
                    )
                    tx = await self.transaction_service.get_transaction(transaction_id)
                    return VerificationSubmitResult(
                        refreshed, VerificationOutcome.SUCCEEDED, tx.state, decision
                    )
            raise VerificationError(
                "Verification resolution is currently in progress. Please retry.",
                code="VERIFICATION_IN_PROGRESS",
                status_code=409,
            )

        # 3. Status must be PENDING
        if challenge.status != "PENDING":
            raise VerificationError(
                "Verification challenge is no longer active",
                code="VERIFICATION_ALREADY_RESOLVED",
                status_code=409,
            )

        # 4. Transaction state consistency check (SEC-04):
        # Transaction must currently be in VERIFICATION_REQUIRED
        tx = await self.transaction_service.get_transaction(transaction_id)
        if tx.state != TransactionState.VERIFICATION_REQUIRED.value:
            if tx.state in (
                TransactionState.SETTLED_SIMULATED.value,
                TransactionState.CANCELLED_SIMULATED.value,
            ):
                raise VerificationError(
                    f"Transaction is in terminal state '{tx.state}' and cannot be verified",
                    code="TRANSACTION_TERMINAL",
                    status_code=409,
                )
            raise VerificationError(
                f"Transaction does not currently require verification (state: '{tx.state}')",
                code="VERIFICATION_NOT_REQUIRED",
                status_code=409,
            )

        # 5. Check server-side expiry
        now = datetime.now(UTC)
        if challenge.expires_at <= now:
            await self.repository.update_challenge_fields(
                cid, challenge.version, {"status": "EXPIRED"}
            )
            raise VerificationError(
                "Verification challenge has expired",
                code="VERIFICATION_EXPIRED",
                status_code=400,
            )

        # 6. Verify OTP
        if verify_otp(otp, challenge.otp_digest, self.settings):
            return await self._handle_correct(challenge, transaction_id)
        return await self._handle_incorrect(challenge, transaction_id)

    async def _handle_correct(
        self, challenge: VerificationChallengeModel, transaction_id: UUID
    ) -> VerificationSubmitResult:
        cid = challenge.id
        current_version = challenge.version

        # Attempt optimistic claim up to 3 times to handle races against
        # attempt_count increments (SEC-02).
        won = False
        active_challenge = challenge
        for _ in range(3):
            won = await self.repository.update_challenge_fields(
                cid,
                current_version,
                {"status": "VERIFIED", "verified_at": datetime.now(UTC)},
            )
            if won:
                break
            # Lost race: check why
            refreshed = await self.repository.get_challenge_by_id(cid)
            if refreshed is None:
                break
            active_challenge = refreshed
            if refreshed.status == "PENDING" and refreshed.attempt_count < refreshed.max_attempts:
                # An incorrect attempt bumped attempt_count/version; retry with new version.
                current_version = refreshed.version
                continue
            break

        if not won:
            # Another request won the lock and is resolving or already resolved
            refreshed = await self.repository.get_challenge_by_id(cid)
            if refreshed and refreshed.status in ("VERIFIED", "CONSUMED"):
                # Bounded wait for winning request's decision
                for _ in range(30):
                    if refreshed is not None and refreshed.decision_id is not None:
                        break
                    await asyncio.sleep(0.1)
                    refreshed = await self.repository.get_challenge_by_id(cid)

                if refreshed and refreshed.decision_id is not None:
                    decision = await self.repository.get_latest_decision_for_transaction(
                        transaction_id
                    )
                    tx = await self.transaction_service.get_transaction(transaction_id)
                    return VerificationSubmitResult(
                        refreshed, VerificationOutcome.SUCCEEDED, tx.state, decision
                    )

            raise VerificationError(
                "Verification resolution is in progress or already processed. Please retry.",
                code="VERIFICATION_IN_PROGRESS",
                status_code=409,
            )

        # Won lock and set status="VERIFIED". Now resolve through workflow service.
        try:
            decision, tx, _ = await self.workflow_service.resolve_after_verification(
                transaction_id, VerificationOutcome.SUCCEEDED
            )
            await self.repository.set_challenge_decision(cid, decision.id, "CONSUMED")
            refreshed = await self.repository.get_challenge_by_id(cid)
            logger.info(
                "Verification SUCCEEDED for challenge %s tx=%s -> decision action=%s state=%s",
                cid,
                transaction_id,
                decision.action,
                tx.state,
            )
            return VerificationSubmitResult(
                refreshed or active_challenge, VerificationOutcome.SUCCEEDED, tx.state, decision
            )
        except Exception as exc:
            # Partial failure recovery (SEC-04): ensure challenge is NOT stranded in VERIFIED.
            logger.error(
                "Failed to resolve transaction %s after verification: %s",
                transaction_id,
                exc,
            )
            refreshed = await self.repository.get_challenge_by_id(cid)
            if refreshed and refreshed.status == "VERIFIED" and refreshed.decision_id is None:
                await self.repository.update_challenge_fields(
                    cid,
                    refreshed.version,
                    {"status": "FAILED", "failure_reason": "RESOLUTION_FAILED"},
                )
            raise

    async def _handle_incorrect(
        self, challenge: VerificationChallengeModel, transaction_id: UUID
    ) -> VerificationSubmitResult:
        cid = challenge.id
        current_version = challenge.version
        current_attempt_count = challenge.attempt_count
        max_attempts = challenge.max_attempts

        new_count = current_attempt_count + 1
        exhausted = new_count >= max_attempts
        won = await self.repository.update_challenge_fields(
            cid,
            current_version,
            {
                "attempt_count": new_count,
                "status": "FAILED" if exhausted else "PENDING",
                "failure_reason": "ATTEMPTS_EXHAUSTED" if exhausted else "INCORRECT_OTP",
            },
        )
        if not won:
            # Concurrent change; re-fetch cleanly without accessing expired ORM attributes (SEC-01)
            refreshed = await self.repository.get_challenge_by_id(cid)
            tx = await self.transaction_service.get_transaction(transaction_id)
            return VerificationSubmitResult(
                refreshed or challenge, VerificationOutcome.FAILED, tx.state, None
            )

        if not exhausted:
            refreshed = await self.repository.get_challenge_by_id(cid)
            tx = await self.transaction_service.get_transaction(transaction_id)
            return VerificationSubmitResult(
                refreshed or challenge, VerificationOutcome.FAILED, tx.state, None
            )

        # Exhausted: re-evaluate under policy (never settles; escalates to hold).
        try:
            decision, tx, _ = await self.workflow_service.resolve_after_verification(
                transaction_id, VerificationOutcome.EXHAUSTED
            )
            await self.repository.set_challenge_decision(cid, decision.id, "FAILED")
            refreshed = await self.repository.get_challenge_by_id(cid)
            logger.info(
                "Verification EXHAUSTED for challenge %s tx=%s -> decision action=%s state=%s",
                cid,
                transaction_id,
                decision.action,
                tx.state,
            )
            return VerificationSubmitResult(
                refreshed or challenge, VerificationOutcome.EXHAUSTED, tx.state, decision
            )
        except Exception as exc:
            logger.error("Failed to escalate exhausted challenge %s: %s", cid, exc)
            raise

    async def _load_bound_challenge(
        self, transaction_id: UUID, challenge_id: UUID
    ) -> VerificationChallengeModel:
        # Ensure the transaction exists (consistent 404s).
        await self.transaction_service.get_transaction(transaction_id)
        challenge = await self.repository.get_challenge_by_id(challenge_id)
        if challenge is None or challenge.transaction_id != transaction_id:
            raise VerificationError(
                "Verification challenge not found for this transaction",
                code="VERIFICATION_CHALLENGE_INVALID",
                status_code=404,
            )
        return challenge
