"""Decision-ready layer on top of city adapter reports.

Maps city-specific ``compliance_verdict`` tokens into a small normalized
``verdict`` agents can branch on, plus summary, confidence, freshness, and
source links. Raw adapter fields are preserved at the top level and copied
under ``records`` for structured access.
"""

from __future__ import annotations

import re
from typing import Any

from app.city_compliance.coverage import (
    MODE_LICENSE,
    MODE_LICENSE_AND_VIOLATIONS,
    MODE_NONE,
    MODE_VIOLATIONS_ONLY,
    allows_not_licensed_verdict,
    coverage_note_for,
    product_mode_for_city,
)

# Normalized verdicts agents should branch on (stable contract).
VERDICT_LICENSED = "licensed"
VERDICT_NOT_LICENSED = "not_licensed"
VERDICT_EXPIRED = "expired"
VERDICT_VIOLATIONS_OPEN = "violations_open"
VERDICT_NO_VIOLATIONS_FOUND = "no_violations_found"
VERDICT_FLAGGED = "flagged"
VERDICT_UNKNOWN = "unknown"

_LICENSED_ACTIVE = frozenset(
    {
        "licensed_clean",
        "licensed_active",
        "licensed_with_violations",
        "registered_active",
        "registered_clean",
        "registered_with_violations",
        "str_licensed_active",
    }
)
_LICENSED_INACTIVE = frozenset(
    {
        "registered_inactive",
        "str_licensed_inactive",
        "license_not_active",
        "license_inactive_with_violations",
    }
)
_NOT_LICENSED = frozenset(
    {
        "unlicensed",
        "unregistered",
        "str_unlicensed",
        "no_license_or_active_violations_found",
        "no_nov_found",
        "no_cases_found",
        "no_violations_found",
        "no_open_violations",
        "no_open_code_cases",
    }
)
_VIOLATIONS_OPEN = frozenset(
    {
        "violations_open",
        "cases_open",
        "nov_active",
        "open_code_cases",
        "unregistered_with_violations",
        "unlicensed_with_violations",
    }
)
_VIOLATIONS_HISTORY = frozenset(
    {
        "violations_closed_only",
        "cases_closed_only",
        "nov_historical_only",
    }
)
_FLAGGED = frozenset({"condemned_or_boarded"})
_INVALID = frozenset({"invalid_address"})


def normalize_address_for_match(address: str) -> str:
    """Uppercase, collapse whitespace, strip common unit suffix noise."""
    text = (address or "").strip().upper()
    text = re.sub(r"\s+", " ", text)
    return text


def open_violation_count(report: dict[str, Any]) -> int | None:
    viol = report.get("violation_cases") or {}
    if not isinstance(viol, dict):
        return None
    for key in ("open", "open_count", "openish_count", "active_count"):
        if key not in viol:
            continue
        val = viol.get(key)
        if val is None:
            continue
        try:
            return int(val)
        except (TypeError, ValueError):
            return None
    recent = viol.get("recent")
    if isinstance(recent, list) and recent:
        openish = 0
        for row in recent:
            if not isinstance(row, dict):
                continue
            status = " ".join(
                str(row.get(k) or "")
                for k in (
                    "case_status",
                    "status",
                    "violation_status",
                    "inspection_result",
                )
            ).lower()
            if any(tok in status for tok in ("open", "enforce", "active", "violation")):
                if "closed" not in status and "abate" not in status:
                    openish += 1
        return openish if openish else 0
    total = viol.get("total")
    if total == 0:
        return 0
    return None


def normalized_verdict(
    compliance_verdict: str | None,
    report: dict[str, Any],
    *,
    product_mode: str | None = None,
) -> str:
    mode = product_mode or product_mode_for_city(
        str(report.get("city") or ""), report
    )
    token = (compliance_verdict or "").strip().lower()

    if mode == MODE_NONE:
        return VERDICT_UNKNOWN

    if token in _INVALID:
        return VERDICT_UNKNOWN
    if token in _FLAGGED:
        return VERDICT_FLAGGED

    if mode == MODE_VIOLATIONS_ONLY:
        if token in _VIOLATIONS_OPEN or token in {
            "unregistered_with_violations",
            "unlicensed_with_violations",
        }:
            return VERDICT_VIOLATIONS_OPEN
        if token in _VIOLATIONS_HISTORY or token in {
            "no_violations_found",
            "no_open_violations",
            "no_open_code_cases",
            "no_cases_found",
            "no_nov_found",
            "violations_closed_only",
            "cases_closed_only",
            "nov_historical_only",
        }:
            return VERDICT_NO_VIOLATIONS_FOUND
        open_n = open_violation_count(report)
        if open_n and open_n > 0:
            return VERDICT_VIOLATIONS_OPEN
        if open_n == 0:
            return VERDICT_NO_VIOLATIONS_FOUND
        return VERDICT_UNKNOWN

    # License or license+violations products
    if token in _VIOLATIONS_OPEN:
        return VERDICT_VIOLATIONS_OPEN
    if token in _LICENSED_INACTIVE:
        return VERDICT_EXPIRED
    if token in _LICENSED_ACTIVE:
        open_n = open_violation_count(report)
        if open_n and open_n > 0:
            return VERDICT_VIOLATIONS_OPEN
        return VERDICT_LICENSED
    if token in _NOT_LICENSED:
        if allows_not_licensed_verdict(mode):
            open_n = open_violation_count(report)
            if open_n and open_n > 0:
                return VERDICT_VIOLATIONS_OPEN
            return VERDICT_NOT_LICENSED
        return VERDICT_UNKNOWN
    if token in _VIOLATIONS_HISTORY:
        if allows_not_licensed_verdict(mode):
            return VERDICT_NOT_LICENSED
        return VERDICT_NO_VIOLATIONS_FOUND

    if report.get("registered") is True or report.get("licensed") is True:
        open_n = open_violation_count(report)
        if open_n and open_n > 0:
            return VERDICT_VIOLATIONS_OPEN
        return VERDICT_LICENSED
    if report.get("registered") is False or report.get("licensed") is False:
        if allows_not_licensed_verdict(mode):
            return VERDICT_NOT_LICENSED
        return VERDICT_UNKNOWN
    return VERDICT_UNKNOWN


def _registration_status_is_active(status: str) -> bool:
    text = (status or "").lower().strip()
    if not text:
        return False
    if "inactive" in text or "expired" in text or "not active" in text:
        return False
    if text.startswith("registered") and "unregistered" not in text:
        return True
    return "active" in text


def _best_registration(registrations: list[Any]) -> dict[str, Any] | None:
    if not registrations:
        return None
    for row in registrations:
        if isinstance(row, dict) and _registration_status_is_active(
            str(row.get("status") or "")
        ):
            return row
    first = registrations[0]
    return first if isinstance(first, dict) else None


def key_dates(report: dict[str, Any]) -> dict[str, str | None]:
    reg = _best_registration(report.get("registrations") or [])
    licenses = report.get("rental_licenses") or []
    lic = _best_registration(licenses if isinstance(licenses, list) else [])
    source = reg or lic or {}
    return {
        "issued": _pick_date(
            source,
            "issue_date",
            "registered_date",
            "license_issue_date",
            "license_date",
            "issued_date",
            "last_registration_date",
            "start_date",
        ),
        "expires": _pick_date(
            source,
            "expiration_date",
            "expires_date",
            "expiry_date",
            "license_expiration_date",
            "registration_end_date",
            "expire_date",
            "next_renew_date",
        ),
    }


def _pick_date(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def source_url_from_report(report: dict[str, Any]) -> str | None:
    registrations = report.get("registrations") or []
    for row in registrations:
        if isinstance(row, dict):
            url = row.get("record_url") or row.get("link")
            if url:
                return str(url)
    sources = report.get("sources") or []
    if sources:
        return str(sources[0])
    return None


def data_as_of(report: dict[str, Any]) -> str | None:
    generated = report.get("generated_at")
    if generated:
        return str(generated)
    return None


def confidence_for(
    report: dict[str, Any],
    *,
    address: str,
    product_mode: str,
    verdict: str,
) -> str:
    if product_mode == MODE_NONE or verdict == VERDICT_UNKNOWN:
        return "low"
    queried = normalize_address_for_match(str(report.get("address_queried") or address))
    if not queried:
        return "low"
    registrations = report.get("registrations") or []
    licenses = report.get("rental_licenses") or []
    rows = [r for r in (*registrations, *licenses) if isinstance(r, dict)]
    if product_mode == MODE_VIOLATIONS_ONLY:
        viol = report.get("violation_cases") or {}
        if isinstance(viol, dict) and (viol.get("total") or viol.get("recent")):
            return "medium"
        return "low"
    if not rows and not report.get("violation_cases"):
        return "medium"
    for row in rows:
        row_addr = normalize_address_for_match(str(row.get("address") or ""))
        if row_addr and (queried in row_addr or row_addr in queried):
            return "high"
    if rows:
        return "medium"
    viol = report.get("violation_cases") or {}
    if isinstance(viol, dict) and viol.get("total"):
        return "medium"
    return "low"


def summary_sentence(
    *,
    city_name: str | None,
    verdict: str,
    compliance_verdict: str | None,
    open_count: int | None,
    registered: bool | None,
    product_mode: str,
) -> str:
    place = city_name or "This city"
    if product_mode == MODE_NONE:
        return (
            f"{place}: no live open-data licensing feed is wired for this product; "
            "status is unknown — not a determination that rental is unlicensed or illegal."
        )
    if verdict == VERDICT_FLAGGED:
        return f"{place}: public records flag condemned or boarded conditions at this address."
    if verdict == VERDICT_VIOLATIONS_OPEN:
        n = open_count if open_count is not None else "open"
        if product_mode == MODE_VIOLATIONS_ONLY:
            return (
                f"{place}: open code-enforcement case(s) found in the violations feed "
                f"({n} open in this snapshot). Does not prove rental license status."
            )
        return (
            f"{place}: open housing-code or enforcement activity found "
            f"({n} open case(s) in the returned snapshot)."
        )
    if verdict == VERDICT_NO_VIOLATIONS_FOUND:
        return (
            f"{place}: no open violations in the enforcement feed returned for this address "
            "(closed/historical cases may still appear in records)."
        )
    if verdict == VERDICT_LICENSED:
        return f"{place}: an active rental or registration license match was found for this address."
    if verdict == VERDICT_EXPIRED:
        return (
            f"{place}: a license or registration record exists but appears inactive or expired."
        )
    if verdict == VERDICT_NOT_LICENSED:
        return f"{place}: no active rental license or registration match was found in city records."
    if verdict == VERDICT_UNKNOWN:
        return (
            f"{place}: this product's feeds do not support a licensing determination for this address."
        )
    if registered is True:
        return f"{place}: registration data was returned; review records for status details."
    return f"{place}: compliance status could not be determined reliably from the returned records."


def build_records_blob(report: dict[str, Any]) -> dict[str, Any]:
    """Structured copy of raw adapter fields (does not remove top-level compat keys)."""
    keys = (
        "registrations",
        "violation_cases",
        "condemned_or_boarded",
        "rental_licenses",
        "licensed",
        "active_registrations",
        "active_licenses",
        "product_scope",
    )
    out: dict[str, Any] = {}
    for key in keys:
        if key in report:
            out[key] = report[key]
    return out


def enrich_decision(
    report: dict[str, Any],
    *,
    city_name: str | None = None,
    address_fallback: str = "",
) -> dict[str, Any]:
    """Return a shallow copy of ``report`` with decision-ready fields added."""
    out = dict(report)
    city_code = str(out.get("city") or "")
    product_mode = product_mode_for_city(city_code, out)
    compliance = out.get("compliance_verdict")
    verdict = normalized_verdict(
        str(compliance) if compliance is not None else None,
        out,
        product_mode=product_mode,
    )
    open_count = open_violation_count(out)
    registered = out.get("registered")
    if registered is None:
        registered = out.get("licensed")

    out["product_mode"] = product_mode
    out["coverage_note"] = coverage_note_for(
        product_mode,
        verdict=verdict,
        compliance_verdict=str(compliance) if compliance is not None else None,
    )
    out["verdict"] = verdict
    out["summary"] = summary_sentence(
        city_name=city_name or out.get("city_name"),
        verdict=verdict,
        compliance_verdict=str(compliance) if compliance is not None else None,
        open_count=open_count,
        registered=registered if isinstance(registered, bool) else None,
        product_mode=product_mode,
    )
    out["key_dates"] = key_dates(out)
    out["open_violations_count"] = open_count
    out["confidence"] = confidence_for(
        out,
        address=str(out.get("address_queried") or address_fallback),
        product_mode=product_mode,
        verdict=verdict,
    )
    out["data_as_of"] = data_as_of(out)
    out["source_url"] = source_url_from_report(out)
    out["records"] = build_records_blob(out)
    return out
