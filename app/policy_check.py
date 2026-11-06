"""Offline buyer payment-policy consistency inspector (`x402.policy_check`).

Evaluates caller-supplied PAYMENT-REQUIRED wire (merchant/inspected) against an
explicit buyer policy. This service's **own** fee is authorized only via a
separate server-built challenge — never via the inspected header.

See docs/superpowers/specs/2026-11-06-x402-policy-check-design.md
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator
from x402.http import decode_payment_required_header

from app import challenge_cache
from app.commerce_payment import expected_usdc_asset
from app.config import settings
from app.models import BuildSellerRequirementsInput
from app.x402_services import _clamp_description, build_seller_requirements

log = logging.getLogger("policy_check")

PRODUCT_ID = "policy-check-analysis"
SERVICE_NAME = "Policy Check"  # <= 32 for Bazaar
SERVICE_TAGS = ["x402", "policy", "compliance", "buyer", "offline"]
POLICY_SCHEMA_VERSION = 1
EVALUATOR_VERSION = 1

# Bounded untrusted input (spec §4.4)
DEFAULT_MAX_HEADER_BYTES = 65536
DEFAULT_MAX_DECODED_BYTES = 262144
DEFAULT_MAX_ACCEPTS = 16

_RESOURCE_DESCRIPTION = (
    "Offline x402 policy consistency check: POST JSON with inspected "
    "payment_required_header (merchant PAYMENT-REQUIRED wire) and buyer policy. "
    "Returns pass/fail/inconclusive per accept option — not merchant settlement proof."
)

DISCOVERY_INPUT_EXAMPLE: dict[str, Any] = {
    "payment_required_header": "<base64 PAYMENT-REQUIRED from merchant>",
    "policy": {"allowed_networks": ["eip155:84532"], "max_amount_atomic": "10000000"},
    "request_digest": {"canonical_url": "https://example.com/api", "http_method": "GET"},
    "idempotency_key": "optional-client-key",
}

DISCOVERY_OUTPUT_EXAMPLE: dict[str, Any] = {
    "verdict": "pass",
    "policy_schema_version": POLICY_SCHEMA_VERSION,
    "evaluator_version": EVALUATOR_VERSION,
    "accepts_evaluated": 1,
    "option_results": [{"index": 0, "passed": True, "reasons": []}],
    "matching_accept_indexes": [0],
    "selected_eligible_index": 0,
    "decoded_summary": {"x402_version": 2, "accepts_count": 1},
    "analysis_receipt": {"schema_version": 1, "digest_sha256": "…"},
    "note": "Policy consistency only; not settlement proof.",
}

# Example output after payment (includes settlement summary for the **own** fee).
DISCOVERY_PAID_OUTPUT_EXAMPLE: dict[str, Any] = {
    **DISCOVERY_OUTPUT_EXAMPLE,
    "own_service_settlement": {
        "payment_settled": True,
        "payer": "0x…",
        "transaction": "0x…",
    },
}


def max_header_bytes() -> int:
    return int(getattr(settings, "policy_check_max_header_bytes", DEFAULT_MAX_HEADER_BYTES))


def max_decoded_bytes() -> int:
    return int(getattr(settings, "policy_check_max_decoded_bytes", DEFAULT_MAX_DECODED_BYTES))


def max_accepts() -> int:
    return int(getattr(settings, "policy_check_max_accepts", DEFAULT_MAX_ACCEPTS))


def resource_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/x402/policy-check"


def clamped_description() -> str:
    return _clamp_description(_RESOURCE_DESCRIPTION)


Verdict = Literal["pass", "fail", "inconclusive"]


def _empty_frozenset() -> frozenset[str]:
    return frozenset()


class BuyerPolicy(BaseModel):
    """Buyer intent (not cryptographically authenticated)."""

    model_config = ConfigDict(frozen=True)

    allowed_networks: frozenset[str] | None = None
    allowed_pay_to: frozenset[str] | None = None
    allowed_assets: frozenset[str] | None = None
    allowed_schemes: frozenset[str] | None = None
    max_amount_atomic: int | None = None
    max_timeout_seconds: int | None = None
    require_matching_resource: bool = False
    expected_http_method: str | None = None
    expected_extra_sha256: str | None = None

    @field_validator(
        "allowed_networks",
        "allowed_pay_to",
        "allowed_assets",
        "allowed_schemes",
        mode="before",
    )
    @classmethod
    def _coerce_frozenset(cls, v: Any) -> frozenset[str] | None:
        if v is None:
            return None
        if isinstance(v, frozenset):
            return v
        if isinstance(v, (list, tuple, set)):
            return frozenset(str(x).strip() for x in v if str(x).strip())
        raise TypeError("expected a list or set of strings")

    @field_validator("max_amount_atomic", mode="before")
    @classmethod
    def _coerce_max_amount(cls, v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, bool):
            raise TypeError("invalid max_amount_atomic")
        if isinstance(v, int):
            if v < 0:
                raise ValueError("max_amount_atomic must be non-negative")
            return v
        s = str(v).strip()
        if not s.isdigit():
            raise ValueError("max_amount_atomic must be a non-negative integer string")
        return int(s)

    @field_validator("expected_extra_sha256", mode="before")
    @classmethod
    def _norm_extra_hash(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        s = str(v).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", s):
            raise ValueError("expected_extra_sha256 must be 64 hex chars")
        return s


class RequestDigest(BaseModel):
    model_config = ConfigDict(frozen=True)

    canonical_url: str | None = None
    http_method: str | None = None
    body_sha256: str | None = None


class PolicyCheckBody(BaseModel):
    """HTTP / MCP JSON body for the analysis (inspected challenge + policy)."""

    model_config = ConfigDict(extra="forbid")

    payment_required_header: str = Field(..., min_length=1)
    policy: BuyerPolicy
    request_digest: RequestDigest | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


@dataclass
class OptionResult:
    index: int
    passed: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class PolicyCheckResult:
    verdict: Verdict
    option_results: list[OptionResult]
    matching_accept_indexes: list[int]
    selected_eligible_index: int | None
    analysis_input_digest: str
    decoded_summary: dict[str, Any]
    top_reasons: list[dict[str, str]]
    analysis_receipt_digest: str = ""
    policy_schema_version: int = POLICY_SCHEMA_VERSION
    evaluator_version: int = EVALUATOR_VERSION

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "policy_schema_version": self.policy_schema_version,
            "evaluator_version": self.evaluator_version,
            "accepts_evaluated": len(self.option_results),
            "option_results": [
                {"index": o.index, "passed": o.passed, "reasons": o.reasons}
                for o in self.option_results
            ],
            "matching_accept_indexes": self.matching_accept_indexes,
            "selected_eligible_index": self.selected_eligible_index,
            "decoded_summary": self.decoded_summary,
            "analysis_receipt": {
                "schema_version": 1,
                "digest_sha256": self.analysis_receipt_digest or None,
            },
            "analysis_input_digest": self.analysis_input_digest,
            "note": "Policy consistency only; not merchant settlement proof.",
        }


def _wire_size_bytes(pr: Any) -> int:
    dumped = (
        pr.model_dump_json(by_alias=True)
        if hasattr(pr, "model_dump_json")
        else json.dumps(
            pr.model_dump(by_alias=True) if hasattr(pr, "model_dump") else pr,
            default=str,
        )
    )
    return len(dumped.encode("utf-8"))


def _parse_positive_int_str(raw: Any) -> tuple[int | None, str | None]:
    """Return (value, error_reason) for requirement amount fields."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, "amount_missing"
    if not s.isdigit():
        return None, "amount_not_integer_string"
    return int(s), None


def _network_family(network: str) -> Literal["evm", "solana", "other"]:
    n = (network or "").strip().lower()
    if n.startswith("eip155:"):
        return "evm"
    if n.startswith("solana:") or n == "solana-mainnet" or n.startswith("solana"):
        return "solana"
    return "other"


def _normalize_evm_address(addr: str | None) -> tuple[str | None, str | None]:
    """Return (normalized, error_reason)."""
    if addr is None:
        return None, None
    s = str(addr).strip()
    if not s:
        return None, None
    if not s.startswith("0x"):
        return None, "evm_address_missing_0x"
    low = s.lower()
    hexpart = low[2:]
    if len(hexpart) != 40 or any(c not in "0123456789abcdef" for c in hexpart):
        return None, "evm_address_malformed"
    return f"0x{hexpart}", None


def _normalize_token_id(network: str, asset: str | None) -> tuple[str | None, str | None]:
    """Normalize asset/pay_to for policy comparison."""
    fam = _network_family(network)
    if asset is None or str(asset).strip() == "":
        return None, None
    s = str(asset).strip()
    if fam == "evm":
        return _normalize_evm_address(s)
    if fam == "solana":
        return s, None
    # other chains: case-sensitive compare
    return s, None


def _canonical_url_key(url: str) -> str:
    try:
        p = urlparse(url.strip())
    except Exception:
        return url.strip().lower()
    scheme = (p.scheme or "").lower()
    netloc = (p.netloc or "").lower()
    path = p.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return f"{scheme}://{netloc}{path}"


def analysis_input_digest(
    *,
    inspected_header_digest: str,
    policy: BuyerPolicy,
    request_digest: RequestDigest | None,
) -> str:
    payload = {
        "inspected_header_digest": inspected_header_digest,
        "policy": json.loads(policy.model_dump_json()),
        "request_digest": json.loads(request_digest.model_dump_json())
        if request_digest
        else None,
        "policy_schema_version": POLICY_SCHEMA_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def analysis_receipt_digest(*, analysis_input_digest: str, payer: str | None, tx: str | None) -> str:
    payload = {
        "analysis_input_digest": analysis_input_digest,
        "payer": (payer or "").lower(),
        "tx": str(tx or ""),
        "product_id": PRODUCT_ID,
        "schema_version": 1,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def inspected_header_digest(header: str) -> str:
    return hashlib.sha256(header.encode("utf-8")).hexdigest()


def evaluate_policy(
    *,
    payment_required_header: str,
    policy: BuyerPolicy,
    request_digest: RequestDigest | None,
) -> PolicyCheckResult:
    top: list[dict[str, str]] = []
    empty = PolicyCheckResult(
        verdict="inconclusive",
        option_results=[],
        matching_accept_indexes=[],
        selected_eligible_index=None,
        analysis_input_digest="",
        decoded_summary={},
        top_reasons=[],
    )

    if len(payment_required_header) > max_header_bytes():
        top.append({"code": "oversized_input", "detail": "payment_required_header too large"})
        empty.top_reasons = top
        return empty

    pr: Any
    try:
        pr = decode_payment_required_header(payment_required_header)
    except Exception as exc:
        log.info("policy_check decode failed: %s", type(exc).__name__)
        top.append({"code": "decode_error", "detail": type(exc).__name__})
        empty.top_reasons = top
        return empty

    if _wire_size_bytes(pr) > max_decoded_bytes():
        top.append({"code": "oversized_decoded", "detail": "decoded PaymentRequired too large"})
        empty.top_reasons = top
        return empty

    x402_ver = getattr(pr, "x402_version", None)
    if x402_ver is not None and x402_ver != 2:
        top.append(
            {
                "code": "unsupported_x402_version",
                "detail": str(x402_ver),
            }
        )
        empty.top_reasons = top
        return empty

    accepts = list(getattr(pr, "accepts", []) or [])
    if len(accepts) > max_accepts():
        top.append({"code": "accepts_too_many", "detail": str(len(accepts))})
        empty.top_reasons = top
        return empty

    resource_obj = getattr(pr, "resource", None)
    resource_url_top = None
    if resource_obj is not None:
        url_get = getattr(resource_obj, "url", None)
        if url_get is None and isinstance(resource_obj, dict):
            url_get = resource_obj.get("url")
        resource_url_top = str(url_get) if url_get else None

    decoded_summary: dict[str, Any] = {
        "x402_version": int(x402_ver) if x402_ver is not None else None,
        "accepts_count": len(accepts),
        "has_resource": resource_obj is not None,
    }

    hdr_digest = inspected_header_digest(payment_required_header)
    input_digest = analysis_input_digest(
        inspected_header_digest=hdr_digest,
        policy=policy,
        request_digest=request_digest,
    )

    global_inconclusive = False
    if request_digest and request_digest.body_sha256:
        top.append(
            {
                "code": "body_binding_not_verifiable_offline",
                "detail": "body_sha256 present",
            }
        )
        global_inconclusive = True

    option_results: list[OptionResult] = []
    matching: list[int] = []

    for i, acc in enumerate(accepts):
        reasons: list[str] = []
        scheme = str(getattr(acc, "scheme", "") or "").strip()
        net = str(getattr(acc, "network", "") or "").strip()

        if policy.allowed_schemes:
            if not scheme:
                reasons.append("scheme_missing")
            elif scheme not in policy.allowed_schemes:
                reasons.append("scheme_not_allowed")

        if net and policy.allowed_networks and net not in policy.allowed_networks:
            reasons.append("network_not_allowed")

        pay_raw = getattr(acc, "pay_to", None)
        if pay_raw is None and hasattr(acc, "model_dump"):
            d = acc.model_dump(by_alias=True)
            pay_raw = d.get("payTo") or d.get("pay_to")
        fam = _network_family(net)
        if policy.allowed_pay_to:
            if not pay_raw:
                reasons.append("pay_to_missing")
            else:
                if fam == "evm":
                    pnorm, perr = _normalize_evm_address(str(pay_raw))
                    if perr:
                        reasons.append(perr)
                    else:
                        allowed_norm = []
                        for a in policy.allowed_pay_to:
                            n, e = _normalize_evm_address(a)
                            if n:
                                allowed_norm.append(n)
                        if pnorm not in set(allowed_norm):
                            reasons.append("pay_to_not_allowed")
                elif fam == "solana":
                    if str(pay_raw) not in policy.allowed_pay_to:
                        reasons.append("pay_to_not_allowed")
                else:
                    reasons.append("unsupported_network_for_address_policy")

        asset_raw = getattr(acc, "asset", None)
        assets_policy = policy.allowed_assets
        if assets_policy is None:
            assets_policy = frozenset()
        if fam == "evm" and len(assets_policy) == 0:
            exp_addr = expected_usdc_asset(net)
            en, _ = _normalize_evm_address(exp_addr)
            if asset_raw is None or str(asset_raw).strip() == "":
                reasons.append("asset_missing")
            else:
                raw_s = str(asset_raw).strip()
                if raw_s.lower() == "usdc" and en:
                    anorm = en
                else:
                    anorm, aerr = _normalize_token_id(net, raw_s)
                    if aerr:
                        reasons.append(aerr)
                if en and anorm is not None and anorm != en:
                    reasons.append("asset_not_usdc_on_network")
        elif assets_policy:
            if not asset_raw:
                reasons.append("asset_missing")
            else:
                anorm, aerr = _normalize_token_id(net, str(asset_raw))
                if aerr:
                    reasons.append(aerr)
                elif anorm is not None:
                    allowed_assets_norm: list[str] = []
                    for a in assets_policy:
                        nn, ee = _normalize_token_id(net, a)
                        if ee:
                            continue
                        if nn is not None:
                            allowed_assets_norm.append(nn)
                    # USDC symbol shortcut on EVM: compare to expected USDC contract
                    if fam == "evm" and str(asset_raw).strip().lower() == "usdc":
                        exp = expected_usdc_asset(net)
                        en, _ = _normalize_evm_address(exp)
                        if en and en == anorm:
                            allowed_assets_norm.append(en)
                    if anorm not in set(allowed_assets_norm):
                        reasons.append("asset_not_allowed")

        amt_val, amt_err = _parse_positive_int_str(getattr(acc, "amount", None))
        if amt_err:
            reasons.append(amt_err)
        elif amt_val is not None and policy.max_amount_atomic is not None:
            if amt_val > int(policy.max_amount_atomic):
                reasons.append("amount_above_max")

        mts = getattr(acc, "max_timeout_seconds", None)
        if mts is not None and policy.max_timeout_seconds is not None:
            try:
                mts_i = int(mts)
                if mts_i > int(policy.max_timeout_seconds):
                    reasons.append("max_timeout_seconds_above_policy_ceiling")
            except (TypeError, ValueError):
                reasons.append("max_timeout_seconds_invalid")

        extra = getattr(acc, "extra", None)
        if policy.expected_extra_sha256 is not None:
            if extra is None:
                reasons.append("extra_missing_for_policy")
            else:
                try:
                    if hasattr(extra, "model_dump"):
                        ex_obj = extra.model_dump()
                    elif isinstance(extra, dict):
                        ex_obj = extra
                    else:
                        ex_obj = dict(extra)
                    ex_dump = json.dumps(
                        ex_obj,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    got = hashlib.sha256(ex_dump.encode("utf-8")).hexdigest()
                    if got != policy.expected_extra_sha256:
                        reasons.append("extra_sha256_mismatch")
                except Exception:
                    reasons.append("extra_canonicalize_failed")

        if policy.require_matching_resource:
            if request_digest is None or not request_digest.canonical_url:
                global_inconclusive = True
                reasons.append("resource_binding_incomplete")
            else:
                cand_urls: list[str] = []
                res = getattr(acc, "resource", None)
                if res is not None:
                    uu = getattr(res, "url", None)
                    if uu:
                        cand_urls.append(str(uu))
                if resource_url_top:
                    cand_urls.append(resource_url_top)
                want = _canonical_url_key(request_digest.canonical_url)
                if not any(_canonical_url_key(c) == want for c in cand_urls):
                    reasons.append("resource_url_mismatch")
            if policy.expected_http_method and request_digest and request_digest.http_method:
                if (
                    str(request_digest.http_method).strip().upper()
                    != policy.expected_http_method.strip().upper()
                ):
                    reasons.append("http_method_mismatch")

        passed = len(reasons) == 0 and not global_inconclusive
        option_results.append(OptionResult(index=i, passed=passed, reasons=reasons))
        if passed:
            matching.append(i)

    if not accepts:
        verdict: Verdict = "inconclusive"
    elif global_inconclusive:
        verdict = "inconclusive"
    elif matching:
        verdict = "pass"
    else:
        verdict = "fail"

    sel = min(matching) if matching else None

    return PolicyCheckResult(
        verdict=verdict,
        option_results=option_results,
        matching_accept_indexes=sorted(matching),
        selected_eligible_index=sel,
        analysis_input_digest=input_digest,
        decoded_summary=decoded_summary,
        top_reasons=top,
    )


def parse_price_usdc() -> float:
    raw = str(settings.policy_check_price).replace("$", "").strip()
    return float(raw)


def price_string() -> str:
    return settings.policy_check_price


def build_payment_required_header() -> str:
    """Server-authored challenge for **this** service fee (analysis delivery)."""
    network = settings.x402_default_network.split(",")[0].strip()
    price = price_string()
    res = resource_url()
    tags = list(SERVICE_TAGS)
    fp = challenge_cache.fingerprint(
        network=network,
        price=price,
        resource=res,
        pay_to=settings.x402_pay_to_address,
        discoverable=settings.bazaar_discoverable,
        description=clamped_description(),
        input_example=DISCOVERY_INPUT_EXAMPLE,
        output_example=DISCOVERY_OUTPUT_EXAMPLE,
        service_name=SERVICE_NAME,
        service_tags=tags,
        method="POST",
    )

    def _build() -> str:
        out = build_seller_requirements(
            BuildSellerRequirementsInput(
                network=network,
                price=price,
                description=clamped_description(),
                resource_url=res,
                mime_type="application/json",
                discovery_method="POST",
                discovery_input_example=DISCOVERY_INPUT_EXAMPLE,
                discovery_output_example=DISCOVERY_OUTPUT_EXAMPLE,
                service_name=SERVICE_NAME,
                service_tags=tags,
            )
        )
        return str(out["payment_required_header"])

    return challenge_cache.get_or_build(PRODUCT_ID, fp, _build)


async def verify_and_settle(payment_signature: str, payment_required: str) -> dict[str, Any]:
    from app.models import VerifyPaymentInput
    from app.x402_services import _verify_and_settle_payment

    return await _verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required,
        )
    )


def run_evaluation(body: PolicyCheckBody) -> PolicyCheckResult:
    result = evaluate_policy(
        payment_required_header=body.payment_required_header,
        policy=body.policy,
        request_digest=body.request_digest,
    )
    return result


def build_paid_analysis_dict(
    body: PolicyCheckBody,
    *,
    settlement: dict[str, Any],
) -> dict[str, Any]:
    """Shared 200 body for HTTP + MCP after successful own-service settle."""
    eval_result = run_evaluation(body)
    tx = settlement.get("transaction") or settlement.get("txHash")
    payer = settlement.get("payer")
    receipt_d = analysis_receipt_digest(
        analysis_input_digest=eval_result.analysis_input_digest,
        payer=str(payer) if payer else None,
        tx=str(tx) if tx else None,
    )
    out = eval_result.to_public_dict()
    out["analysis_receipt"] = {"schema_version": 1, "digest_sha256": receipt_d}
    out["own_service_settlement"] = {
        "payment_settled": True,
        "payer": str(payer) if payer else None,
        "transaction": str(tx) if tx else None,
    }
    return out


# --- Idempotency (Redis when available; in-memory fallback) ---

_IDEM_MEM: dict[str, tuple[str, dict[str, Any]]] = {}
_IDEM_PREFIX = "policy_check:idem:"


def _idem_redis():
    from app import redis_client

    return redis_client.client


def idempotency_strict_redis_unavailable() -> bool:
    return bool(
        getattr(settings, "policy_check_idempotency_redis_strict", True)
        and settings.redis_url
        and _idem_redis() is None
    )


def idempotency_get(key: str) -> tuple[str | None, dict[str, Any] | None]:
    if not key:
        return None, None
    r = _idem_redis()
    composite = hashlib.sha256(key.encode("utf-8")).hexdigest()
    if r is not None:
        try:
            raw = r.get(_IDEM_PREFIX + composite)
            if not raw:
                return None, None
            obj = json.loads(raw)
            dg = obj.get("digest")
            bd = obj.get("body")
            if isinstance(dg, str) and isinstance(bd, dict):
                return dg, bd
            return None, None
        except Exception:
            return None, None
    got = _IDEM_MEM.get(key)
    if got is None:
        return None, None
    digest, body = got
    return digest, body


def idempotency_set(key: str, digest: str, body: dict[str, Any]) -> None:
    r = _idem_redis()
    composite = hashlib.sha256(key.encode("utf-8")).hexdigest()
    payload = json.dumps({"digest": digest, "body": body}, separators=(",", ":"))
    if r is not None:
        try:
            r.set(_IDEM_PREFIX + composite, payload, ex=86400)
        except Exception:
            log.warning("policy_check idempotency redis set failed", exc_info=False)
    else:
        _IDEM_MEM[key] = (digest, body)


def clear_idempotency_test() -> None:
    _IDEM_MEM.clear()


def settle_payer_fingerprint(settlement: dict[str, Any]) -> str:
    payer = str(settlement.get("payer") or "unknown")
    return hashlib.sha256(payer.lower().encode("utf-8")).hexdigest()[:16]


def composite_idempotency_key(payer_fp: str, client_key: str) -> str:
    return f"{payer_fp}:{client_key}"
