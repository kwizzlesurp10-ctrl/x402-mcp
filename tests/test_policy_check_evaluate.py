"""Pure offline `evaluate_policy` matrix (no HTTP, no settlement)."""

from __future__ import annotations

import base64

import pytest
from x402.http import encode_payment_required_header
from x402.schemas import PaymentRequired, PaymentRequirements

from app import policy_check
from app.policy_check import BuyerPolicy, RequestDigest, evaluate_policy


def _minimal_valid_header() -> str:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1000",
        max_timeout_seconds=300,
        extra={},
        description="policy-check test",
    )
    pr = PaymentRequired(x402_version=2, accepts=[req], error="test")
    return encode_payment_required_header(pr)


def test_decode_error_inconclusive() -> None:
    out = evaluate_policy(
        payment_required_header="not-valid-base64@@@",
        policy=BuyerPolicy(),
        request_digest=None,
    )
    assert out.verdict == "inconclusive"
    assert any(r.get("code") == "decode_error" for r in out.top_reasons)


def test_per_accept_independent_no_cross_mix() -> None:
    req_bad = PaymentRequirements(
        scheme="exact",
        network="eip155:1",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1000",
        max_timeout_seconds=300,
        extra={},
    )
    req_ok = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1000",
        max_timeout_seconds=300,
        extra={},
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req_bad, req_ok], error="test")
    )
    policy = BuyerPolicy(allowed_networks=frozenset({"eip155:84532"}))
    out = evaluate_policy(payment_required_header=header, policy=policy, request_digest=None)
    assert out.verdict == "pass"
    assert out.matching_accept_indexes == [1]


def test_amount_integer_string_no_float() -> None:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1e6",
        max_timeout_seconds=300,
        extra={},
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="test")
    )
    policy = BuyerPolicy(max_amount_atomic=10**12)
    out = evaluate_policy(payment_required_header=header, policy=policy, request_digest=None)
    assert out.verdict != "pass"
    assert "amount_not_integer_string" in (out.option_results[0].reasons if out.option_results else [])


@pytest.mark.parametrize(
    "amount,policy_max,ok",
    [
        ("1000000", 999_999, False),
        ("1000000", 1_000_000, True),
    ],
)
def test_amount_ceiling(amount: str, policy_max: int, ok: bool) -> None:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount=amount,
        max_timeout_seconds=300,
        extra={},
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="test")
    )
    policy = BuyerPolicy(max_amount_atomic=policy_max)
    out = evaluate_policy(payment_required_header=header, policy=policy, request_digest=None)
    assert (0 in out.matching_accept_indexes) is ok


def test_evm_pay_to_checksum_normalizes() -> None:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036cbd53842c5426634e7929541ec2318f3dcf7e",
        asset="USDC",
        amount="1",
        max_timeout_seconds=300,
        extra={},
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="test")
    )
    policy = BuyerPolicy(
        allowed_pay_to=frozenset({"0x036CbD53842c5426634e7929541eC2318f3dCF7e"}),
    )
    out = evaluate_policy(payment_required_header=header, policy=policy, request_digest=None)
    assert out.verdict == "pass"


def test_solana_address_case_sensitive() -> None:
    req = PaymentRequirements(
        scheme="exact",
        network="solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1",
        pay_to="SoMeSoLAddRess123",
        asset="TokenMintAddr",
        amount="1",
        max_timeout_seconds=300,
        extra={},
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="test")
    )
    policy = BuyerPolicy(allowed_pay_to=frozenset({"somesoladdress123"}))
    out = evaluate_policy(payment_required_header=header, policy=policy, request_digest=None)
    assert out.verdict == "fail"
    assert "pay_to_not_allowed" in out.option_results[0].reasons


def test_accepts_too_many_inconclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy_check, "max_accepts", lambda: 2)
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1",
        max_timeout_seconds=300,
        extra={},
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req, req, req], error="test")
    )
    out = evaluate_policy(payment_required_header=header, policy=BuyerPolicy(), request_digest=None)
    assert out.verdict == "inconclusive"
    assert any(r.get("code") == "accepts_too_many" for r in out.top_reasons)


def test_body_sha256_makes_inconclusive() -> None:
    header = _minimal_valid_header()
    rd = RequestDigest(canonical_url="https://a.com/x", http_method="GET", body_sha256="a" * 64)
    out = evaluate_policy(
        payment_required_header=header,
        policy=BuyerPolicy(),
        request_digest=rd,
    )
    assert out.verdict == "inconclusive"
    assert any(r.get("code") == "body_binding_not_verifiable_offline" for r in out.top_reasons)


def test_require_matching_resource_fail_and_incomplete_digest() -> None:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1",
        max_timeout_seconds=300,
        extra={},
        resource={"url": "https://merchant.example/paid"},
    )
    header = encode_payment_required_header(
        PaymentRequired(
            x402_version=2,
            resource={"url": "https://merchant.example/other"},
            accepts=[req],
            error="test",
        )
    )
    digest = RequestDigest(canonical_url="https://merchant.example/paid", http_method="POST")
    policy = BuyerPolicy(require_matching_resource=True)
    out = evaluate_policy(
        payment_required_header=header,
        policy=policy,
        request_digest=digest,
    )
    assert "resource_url_mismatch" in out.option_results[0].reasons

    out2 = evaluate_policy(
        payment_required_header=header,
        policy=BuyerPolicy(require_matching_resource=True),
        request_digest=None,
    )
    assert out2.verdict == "inconclusive"


def test_unknown_scheme_option_skipped_unless_policy_restricts() -> None:
    req = PaymentRequirements(
        scheme="weird-scheme",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1",
        max_timeout_seconds=300,
        extra={},
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="test")
    )
    out = evaluate_policy(payment_required_header=header, policy=BuyerPolicy(), request_digest=None)
    assert out.verdict == "pass"

    out2 = evaluate_policy(
        payment_required_header=header,
        policy=BuyerPolicy(allowed_schemes=frozenset({"exact"})),
        request_digest=None,
    )
    assert out2.verdict == "fail"
    assert "scheme_not_allowed" in out2.option_results[0].reasons


def test_unsupported_x402_version_inconclusive() -> None:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1",
        max_timeout_seconds=300,
        extra={},
    )
    pr = PaymentRequired(x402_version=99, accepts=[req], error="test")
    header = encode_payment_required_header(pr)
    out = evaluate_policy(payment_required_header=header, policy=BuyerPolicy(), request_digest=None)
    assert out.verdict == "inconclusive"
    assert any(r.get("code") == "unsupported_x402_version" for r in out.top_reasons)


def test_oversized_header_inconclusive() -> None:
    big = base64.b64encode(b"x" * (policy_check.max_header_bytes() + 1)).decode("ascii")
    out = evaluate_policy(payment_required_header=big, policy=BuyerPolicy(), request_digest=None)
    assert out.verdict == "inconclusive"
    assert any(r.get("code") == "oversized_input" for r in out.top_reasons)


def test_max_timeout_seconds_ceiling() -> None:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1",
        max_timeout_seconds=99999,
        extra={},
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="test")
    )
    policy = BuyerPolicy(max_timeout_seconds=60)
    out = evaluate_policy(payment_required_header=header, policy=policy, request_digest=None)
    assert out.verdict == "fail"
    assert "max_timeout_seconds_above_policy_ceiling" in out.option_results[0].reasons
