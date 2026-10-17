"""Simulated customer verification challenge service (P2-A5).

Issues a SIMULATED OTP challenge for a verification-required transaction, binds
it to a distinct customer verification session, validates submissions securely
(keyed digest, expiry, bounded attempts, single-use consumption under
concurrency), and triggers deterministic policy re-evaluation. Verification is
an additional signal; it never settles a transaction on its own and never
overrides strong fraud evidence.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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

        existing = await self.repository.get_latest_pending_challenge(transaction_id)
        now = datetime.now(UTC)
        if existing is not None:
            if existing.expires_at > now:
                # Active challenge exists: return it (OTP is not re-displayed — not stored).
                token, expires_in = create_customer_verification_token(
                    challenge_id=str(existing.id),
                    transaction_id=str(transaction_id),
                    customer_id=tx.customer_id,
                    settings=self.settings,
                )
                return existing, None, token, expires_in
            # Expired: mark it so a fresh challenge can be issued.
            await self.repository.update_challenge_fields(
                existing.id, existing.version, {"status": "EXPIRED"}
            )

        otp = generate_otp(self.settings.VERIFICATION_OTP_LENGTH)
        challenge = VerificationChallengeModel(
            id=uuid4(),
            transaction_id=transaction_id,
            customer_id=tx.customer_id,
            otp_digest=hash_otp(otp, self.settings),
            status="PENDING",
            attempt_count=0,
            max_attempts=self.settings.VERIFICATION_MAX_ATTEMPTS,
            version=1,
            expires_at=now + timedelta(seconds=self.settings.VERIFICATION_CHALLENGE_TTL_SECONDS),
        )
        saved = await self.repository.create_challenge(challenge)
        token, expires_in = create_customer_verification_token(
            challenge_id=str(saved.id),
            transaction_id=str(transaction_id),
            customer_id=tx.customer_id,
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

        if challenge.customer_id != str(customer_id):
            # Session/customer binding mismatch -> generic 404-style rejection.
            raise VerificationError(
                "Verification challenge not found for this session",
                code="VERIFICATION_CHALLENGE_INVALID",
                status_code=404,
            )

        # Idempotent success replay: already resolved with a decision.
        if challenge.status in ("VERIFIED", "CONSUMED") and challenge.decision_id is not None:
            decision = await self.repository.get_latest_decision_for_transaction(transaction_id)
            tx = await self.transaction_service.get_transaction(transaction_id)
            return VerificationSubmitResult(
                challenge, VerificationOutcome.SUCCEEDED, tx.state, decision
            )

        if challenge.status != "PENDING":
            raise VerificationError(
                "Verification challenge is no longer active",
                code="VERIFICATION_ALREADY_RESOLVED",
                status_code=409,
            )

        now = datetime.now(UTC)
        if challenge.expires_at <= now:
            await self.repository.update_challenge_fields(
                challenge.id, challenge.version, {"status": "EXPIRED"}
            )
            raise VerificationError(
                "Verification challenge has expired",
                code="VERIFICATION_EXPIRED",
                status_code=400,
            )

        if verify_otp(otp, challenge.otp_digest, self.settings):
            return await self._handle_correct(challenge, transaction_id)
        return await self._handle_incorrect(challenge, transaction_id)

    async def _handle_correct(
        self, challenge: VerificationChallengeModel, transaction_id: UUID
    ) -> VerificationSubmitResult:
        # Atomic single-use consumption: only one concurrent request wins.
        won = await self.repository.update_challenge_fields(
            challenge.id,
            challenge.version,
            {"status": "VERIFIED", "verified_at": datetime.now(UTC)},
        )
        if not won:
            # Another request consumed it first (or it changed). Return idempotently.
            refreshed = await self.repository.get_challenge_by_id(challenge.id)
            decision = await self.repository.get_latest_decision_for_transaction(transaction_id)
            tx = await self.transaction_service.get_transaction(transaction_id)
            return VerificationSubmitResult(
                refreshed or challenge, VerificationOutcome.SUCCEEDED, tx.state, decision
            )

        decision, tx, _ = await self.workflow_service.resolve_after_verification(
            transaction_id, VerificationOutcome.SUCCEEDED
        )
        await self.repository.set_challenge_decision(challenge.id, decision.id, "CONSUMED")
        refreshed = await self.repository.get_challenge_by_id(challenge.id)
        logger.info(
            "Verification SUCCEEDED for challenge %s tx=%s -> decision action=%s state=%s",
            challenge.id,
            transaction_id,
            decision.action,
            tx.state,
        )
        return VerificationSubmitResult(
            refreshed or challenge, VerificationOutcome.SUCCEEDED, tx.state, decision
        )

    async def _handle_incorrect(
        self, challenge: VerificationChallengeModel, transaction_id: UUID
    ) -> VerificationSubmitResult:
        new_count = challenge.attempt_count + 1
        exhausted = new_count >= challenge.max_attempts
        won = await self.repository.update_challenge_fields(
            challenge.id,
            challenge.version,
            {
                "attempt_count": new_count,
                "status": "FAILED" if exhausted else "PENDING",
                "failure_reason": "ATTEMPTS_EXHAUSTED" if exhausted else "INCORRECT_OTP",
            },
        )
        if not won:
            # Concurrent change; re-fetch and report current state without double-counting.
            refreshed = await self.repository.get_challenge_by_id(challenge.id)
            tx = await self.transaction_service.get_transaction(transaction_id)
            return VerificationSubmitResult(
                refreshed or challenge, VerificationOutcome.FAILED, tx.state, None
            )

        if not exhausted:
            refreshed = await self.repository.get_challenge_by_id(challenge.id)
            tx = await self.transaction_service.get_transaction(transaction_id)
            return VerificationSubmitResult(
                refreshed or challenge, VerificationOutcome.FAILED, tx.state, None
            )

        # Exhausted: re-evaluate under policy (never settles; escalates to hold).
        decision, tx, _ = await self.workflow_service.resolve_after_verification(
            transaction_id, VerificationOutcome.EXHAUSTED
        )
        await self.repository.set_challenge_decision(challenge.id, decision.id, "FAILED")
        refreshed = await self.repository.get_challenge_by_id(challenge.id)
        logger.info(
            "Verification EXHAUSTED for challenge %s tx=%s -> decision action=%s state=%s",
            challenge.id,
            transaction_id,
            decision.action,
            tx.state,
        )
        return VerificationSubmitResult(
            refreshed or challenge, VerificationOutcome.EXHAUSTED, tx.state, decision
        )

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
