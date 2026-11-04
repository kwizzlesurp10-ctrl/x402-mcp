"""What each city product can and cannot conclude from its open-data feeds."""

from __future__ import annotations

from typing import Any

# product_mode — what the paid check is allowed to assert in ``verdict``.
MODE_LICENSE = "license"
MODE_LICENSE_AND_VIOLATIONS = "license_and_violations"
MODE_VIOLATIONS_ONLY = "violations_only"
MODE_NONE = "none"

# Public + mounted cities. Placeholders (atl, mia) use MODE_NONE.
CITY_PRODUCT_MODE: dict[str, str] = {
    "mn": MODE_LICENSE_AND_VIOLATIONS,
    "moco": MODE_LICENSE_AND_VIOLATIONS,
    "nyc": MODE_LICENSE_AND_VIOLATIONS,
    "sea": MODE_LICENSE,
    "den": MODE_LICENSE,
    "orl": MODE_LICENSE,
    "nola": MODE_LICENSE,
    "atx": MODE_LICENSE,
    "bna": MODE_LICENSE,
    "sd": MODE_LICENSE,
    "chi": MODE_VIOLATIONS_ONLY,
    "bos": MODE_VIOLATIONS_ONLY,
    "phi": MODE_VIOLATIONS_ONLY,
    "kc": MODE_VIOLATIONS_ONLY,
    "lax": MODE_VIOLATIONS_ONLY,
    "gain": MODE_VIOLATIONS_ONLY,
    "sf": MODE_VIOLATIONS_ONLY,
    "atl": MODE_NONE,
    "mia": MODE_NONE,
}

_VIOLATIONS_ONLY_SCOPES = frozenset(
    {
        "building_code_violations",
        "building_property_violations",
        "li_property_maintenance_violations",
        "open_exterior_building_violations",
        "open_code_enforcement_cases",
        "code_complaints_violations_permits",
        "dbi_notices_of_violation",
    }
)


def product_mode_for_city(
    city_code: str | None,
    report: dict[str, Any] | None = None,
) -> str:
    code = (city_code or (report or {}).get("city") or "").strip().lower()
    if code in CITY_PRODUCT_MODE:
        mode = CITY_PRODUCT_MODE[code]
        if mode == MODE_NONE:
            return MODE_NONE
        if report:
            scope = (report.get("product_scope") or "").strip()
            if scope in _VIOLATIONS_ONLY_SCOPES:
                return MODE_VIOLATIONS_ONLY
            extra = report.get("records", {}) if isinstance(report.get("records"), dict) else {}
            scope = scope or str(extra.get("product_scope") or "")
            if scope in _VIOLATIONS_ONLY_SCOPES:
                return MODE_VIOLATIONS_ONLY
            sources = report.get("sources") or []
            if mode == MODE_LICENSE and not sources and not (
                report.get("registrations") or report.get("rental_licenses")
            ):
                viol = report.get("violation_cases") or {}
                if isinstance(viol, dict) and viol.get("note"):
                    note = str(viol["note"]).lower()
                    if "does not" in note or "no open data" in note:
                        return MODE_NONE
        return mode
    if report:
        scope = str(report.get("product_scope") or "")
        if scope in _VIOLATIONS_ONLY_SCOPES:
            return MODE_VIOLATIONS_ONLY
    return MODE_LICENSE


def coverage_note_for(
    product_mode: str,
    *,
    verdict: str,
    compliance_verdict: str | None = None,
) -> str:
    if product_mode == MODE_NONE:
        return (
            "This city endpoint has no live open-data licensing feed wired yet; "
            "verdict is unknown — not evidence that the address is unlicensed or illegal to rent."
        )
    if product_mode == MODE_VIOLATIONS_ONLY:
        return (
            "Violations/enforcement data only — this product does not include rental "
            "license or registration records. Verdict describes code cases, not "
            "whether short-term or long-term rental is permitted."
        )
    if product_mode == MODE_LICENSE_AND_VIOLATIONS:
        return (
            "Combines licensing/registration with violation (and where applicable "
            "condemned/boarded) feeds; verdict may reflect license status and/or open cases."
        )
    return (
        "License or registration feed only; no code-enforcement join in this product "
        "unless noted in violation_cases."
    )


def allows_not_licensed_verdict(product_mode: str) -> bool:
    return product_mode in (MODE_LICENSE, MODE_LICENSE_AND_VIOLATIONS)
