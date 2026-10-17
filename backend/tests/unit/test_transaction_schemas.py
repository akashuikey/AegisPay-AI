"""Unit tests for transaction Pydantic validation schemas and payload hashing."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.state_machine import ActorType, TransactionState
from app.schemas.transaction import (
    CreateTransactionRequest,
    TransitionTransactionRequest,
)


def test_valid_create_transaction_request() -> None:
    """Verify valid creation request parses correctly with strip whitespace."""
    req = CreateTransactionRequest(
        customer_id="  cust_1001  ",
        idempotency_key="  tx_key_1  ",
        amount=Decimal("15000.50"),
        currency="inr",
        payment_rail="upi",
        recipient_name="  Aegis Merchant  ",
        recipient_identifier="merchant@upi",
        purpose="  Payment for services  ",
    )
    assert req.customer_id == "cust_1001"
    assert req.idempotency_key == "tx_key_1"
    assert req.amount == Decimal("15000.50")
    assert req.currency == "inr"
    assert req.payment_rail == "upi"
    assert req.recipient_name == "Aegis Merchant"
    assert req.purpose == "Payment for services"


def test_create_transaction_negative_or_zero_amount() -> None:
    """Verify amount <= 0 is rejected by schema validation."""
    with pytest.raises(ValidationError):
        CreateTransactionRequest(
            customer_id="cust_1001",
            idempotency_key="tx_key_1",
            amount=Decimal("0.00"),
            payment_rail="UPI",
            recipient_name="Recipient",
            recipient_identifier="recip@upi",
        )

    with pytest.raises(ValidationError):
        CreateTransactionRequest(
            customer_id="cust_1001",
            idempotency_key="tx_key_1",
            amount=Decimal("-100.50"),
            payment_rail="UPI",
            recipient_name="Recipient",
            recipient_identifier="recip@upi",
        )


def test_payload_hash_determinism() -> None:
    """Verify canonical payload hash produces consistent SHA-256 hashes
    regardless of field input whitespace.
    """
    req1 = CreateTransactionRequest(
        customer_id="cust_1",
        idempotency_key="key_1",
        amount=Decimal("500.00"),
        currency="INR",
        payment_rail="UPI",
        recipient_name="Merchant A",
        recipient_identifier="merchant@upi",
        purpose="Invoice 123",
    )
    req2 = CreateTransactionRequest(
        customer_id="cust_1",
        idempotency_key="key_1",
        amount=Decimal("500.00"),
        currency="inr",
        payment_rail="upi",
        recipient_name="Merchant A",
        recipient_identifier="merchant@upi",
        purpose="Invoice 123",
    )
    assert req1.compute_payload_hash() == req2.compute_payload_hash()


def test_payload_hash_differentiation() -> None:
    """Verify different amounts or recipients produce different hashes."""
    req1 = CreateTransactionRequest(
        customer_id="cust_1",
        idempotency_key="key_1",
        amount=Decimal("500.00"),
        currency="INR",
        payment_rail="UPI",
        recipient_name="Merchant A",
        recipient_identifier="merchant@upi",
    )
    req2 = CreateTransactionRequest(
        customer_id="cust_1",
        idempotency_key="key_1",
        amount=Decimal("500.01"),  # 1 paisa difference
        currency="INR",
        payment_rail="UPI",
        recipient_name="Merchant A",
        recipient_identifier="merchant@upi",
    )
    assert req1.compute_payload_hash() != req2.compute_payload_hash()


def test_transition_request_defaults() -> None:
    """Verify TransitionTransactionRequest defaults to ActorType.SYSTEM."""
    req = TransitionTransactionRequest(target_state=TransactionState.ASSESSING)
    assert req.target_state == TransactionState.ASSESSING
    assert req.actor_type == ActorType.SYSTEM
    assert req.reason is None
