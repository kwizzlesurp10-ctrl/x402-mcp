"""The five swarm roles. Each maps onto a dashboard agent lane and emits its
phase to the shared SSE stream so activity is visible live.

    scout      → discover cheap upstream x402 services
    warden     → enforce ledger/policy.json spend caps + network/domain rules
    treasurer  → pay_and_fetch approved services, write spend (cost basis)
    archivist  → compose the purchases into a priced composite product
    merchant   → build seller requirements to list the composite for sale
"""

from __future__ import annotations

import uuid
from typing import Any

from app import x402_services
from app.config import settings
from app.models import (
    BuildSellerRequirementsInput,
    DiscoverServicesInput,
    GetPaymentRequirementsInput,
    PayAndFetchInput,
)
from app.ops_events import emit_swarm_step
from app.swarm import ledger_writer, policy as policy_mod
from app.swarm.models import Candidate, CompositeProduct, Purchase, SwarmRun


def _parse_accepts(accepts: list[dict[str, Any]]) -> tuple[float | None, str | None]:
    """Pick the cheapest payment option; return (price_usdc, network)."""
    if not accepts:
        return None, None
    best = min(accepts, key=lambda a: int(a.get("amount", 10**12) or 10**12))
    try:
        price = int(best.get("amount", 0)) / 1_000_000
    except (TypeError, ValueError):
        price = None
    return price, best.get("network")


def _parse_bazaar_item(item: dict[str, Any]) -> Candidate | None:
    url = (
        item.get("resource")
        or item.get("url")
        or item.get("endpoint")
        or item.get("resourceUrl")
    )
    if not url:
        return None
    price, network = _parse_accepts(item.get("accepts") or [])
    title = str(item.get("name") or item.get("title") or "")
    return Candidate(
        url=str(url), price_usdc=price, network=network, source="bazaar", title=title
    )


async def _probe_config_url(url: str) -> Candidate:
    """Learn price/network for a configured upstream URL via a keyless 402 probe."""
    price: float | None = None
    network: str | None = None
    try:
        probe = await x402_services.get_payment_requirements(
            GetPaymentRequirementsInput(url=url)
        )
        decoded = probe.get("payment_required_decoded") or {}
        accepts = decoded.get("accepts") if isinstance(decoded, dict) else None
        price, network = _parse_accepts(accepts or [])
    except Exception:  # noqa: BLE001 — probe is best-effort; warden vetoes unknowns
        pass
    return Candidate(
        url=url,
        price_usdc=price,
        network=network or settings.x402_default_network,
        source="config",
    )


async def _discover(query: str | None, max_price_usdc: float) -> list[Candidate]:
    result = await x402_services.discover_services(
        DiscoverServicesInput(query=query, limit=25, max_price_usdc=max_price_usdc)
    )
    out: list[Candidate] = []
    for item in result.get("services", []):
        parsed = _parse_bazaar_item(item)
        if parsed:
            out.append(parsed)
    return out


async def scout(run: SwarmRun, topic: str, max_price_usdc: float) -> list[Candidate]:
    """Discover cheap upstream services; fall back to configured URLs.

    discover_services matches the query as a strict substring, so a multi-word
    topic often matches nothing — fall back to the broad catalog so warden and
    the price cap still have candidates to work with.
    """
    candidates: list[Candidate] = []
    try:
        candidates = await _discover(topic, max_price_usdc)
        if not candidates:
            first_term = topic.split()[0] if topic.split() else None
            candidates = await _discover(first_term, max_price_usdc)
        if not candidates:
            candidates = await _discover(None, max_price_usdc)
    except Exception as exc:  # noqa: BLE001
        run.steps.append({"role": "scout", "warning": f"discovery failed: {exc}"})

    if not candidates:
        urls = [u.strip() for u in settings.swarm_upstream_urls.split(",") if u.strip()]
        for url in urls:
            candidates.append(await _probe_config_url(url))

    run.candidates = candidates
    emit_swarm_step(
        run_id=run.run_id,
        role="scout",
        phase="scouting",
        action="discover_services",
        detail={"found": len(candidates), "topic": topic},
    )
    return candidates


def warden_review(
    run: SwarmRun,
    candidates: list[Candidate],
    policy: policy_mod.Policy,
    max_calls: int,
) -> list[Candidate]:
    """Approve up to max_calls candidates within policy caps; log vetoes."""
    spent_today, spent_month = policy_mod.spend_totals()
    approved: list[Candidate] = []
    for cand in candidates:
        if len(approved) >= max_calls:
            break
        reason = policy_mod.review_purchase(
            policy,
            url=cand.url,
            price_usdc=cand.price_usdc,
            network=cand.network,
            spent_today=spent_today,
            spent_month=spent_month,
        )
        if reason:
            run.vetoes.append({"url": cand.url, "reason": reason})
            emit_swarm_step(
                run_id=run.run_id,
                role="warden",
                phase="vetoed",
                action="policy_veto",
                detail={"url": cand.url, "reason": reason},
            )
            continue
        approved.append(cand)
        # Reserve the projected spend so cumulative caps hold across the batch.
        spent_today += cand.price_usdc or 0.0
        spent_month += cand.price_usdc or 0.0
        emit_swarm_step(
            run_id=run.run_id,
            role="warden",
            phase="approved",
            action="policy_approve",
            detail={"url": cand.url, "price_usdc": cand.price_usdc},
        )
    return approved


def _settlement_tx(settlement: dict[str, Any] | None) -> str | None:
    if not isinstance(settlement, dict):
        return None
    for key in ("transaction", "txHash", "tx_hash", "transactionHash", "tx"):
        val = settlement.get(key)
        if val:
            return str(val)
    return None


async def treasurer_buy(run: SwarmRun, approved: list[Candidate]) -> list[Purchase]:
    """Pay for each approved service and record the spend (cost basis)."""
    purchases: list[Purchase] = []
    for cand in approved:
        network = cand.network or settings.x402_default_network
        try:
            result = await x402_services.pay_and_fetch(
                PayAndFetchInput(url=cand.url, preferred_network=network)
            )
        except ValueError as exc:
            # Hard config error (e.g. missing EVM key) — abort the whole run.
            if "EVM_PRIVATE_KEY" in str(exc):
                raise
            run.steps.append({"role": "treasurer", "warning": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 — soft per-URL failure, keep going
            run.steps.append(
                {"role": "treasurer", "warning": f"{cand.url}: {exc}"}
            )
            continue

        amount = cand.price_usdc or 0.0
        settlement = result.get("payment_settlement")
        settled = bool(result.get("payment_settled"))
        tx = _settlement_tx(settlement)
        purchase = Purchase(
            url=cand.url,
            amount_usdc=amount,
            amount_usdc_atomic=int(round(amount * 1_000_000)),
            network=network,
            settled=settled,
            tx=tx,
            preview=str(result.get("body", ""))[:500],
            title=cand.title,
        )
        purchases.append(purchase)
        ledger_writer.record_spend(
            agent_id=run.agent_id,
            amount_usdc=amount,
            network=network,
            url=cand.url,
            run_id=run.run_id,
            tx=tx,
            settled=settled,
        )
        emit_swarm_step(
            run_id=run.run_id,
            role="treasurer",
            phase="buying",
            action="pay_and_fetch",
            detail={
                "url": cand.url,
                "amount_usdc": amount,
                "settled": settled,
                "tx": tx,
            },
        )
    run.purchases = purchases
    return purchases


def _compose_report(topic: str, purchases: list[Purchase]) -> str:
    lines = [
        f"# Composite Research Report: {topic}",
        "",
        f"Synthesized from {len(purchases)} paid upstream x402 source(s).",
        "",
    ]
    for i, p in enumerate(purchases, 1):
        label = p.title or p.url
        lines.append(f"## Source {i}: {label}")
        lines.append(f"- endpoint: {p.url}")
        lines.append(f"- cost: ${p.amount_usdc:.4f} USDC ({p.network})")
        lines.append("")
        lines.append(p.preview or "(no preview captured)")
        lines.append("")
    return "\n".join(lines)


def archivist_compose(
    run: SwarmRun,
    purchases: list[Purchase],
    topic: str,
    markup: float,
    min_price: float,
    network: str,
) -> CompositeProduct:
    """Compose purchases into one priced composite product (price = cost × markup)."""
    cost_basis = round(sum(p.amount_usdc for p in purchases), 6)
    price = max(round(cost_basis * markup, 6), min_price)
    product = CompositeProduct(
        product_id=uuid.uuid4().hex,
        topic=topic,
        cost_basis_usdc=cost_basis,
        price_usdc=price,
        markup=markup,
        network=network,
        sources=[p.url for p in purchases],
        report=_compose_report(topic, purchases),
        status="draft",
    )
    run.product = product
    emit_swarm_step(
        run_id=run.run_id,
        role="archivist",
        phase="composing",
        action="compose_report",
        detail={
            "product_id": product.product_id,
            "cost_basis_usdc": cost_basis,
            "price_usdc": price,
            "margin_usdc": product.margin_usdc,
        },
    )
    return product


def merchant_list(run: SwarmRun, product: CompositeProduct) -> CompositeProduct:
    """Build x402 seller requirements to list the composite for sale."""
    price_str = f"${product.price_usdc:.2f}"
    requirements = x402_services.build_seller_requirements(
        BuildSellerRequirementsInput(
            network=product.network,
            price=price_str,
            description=f"Composite research report: {product.topic}",
        )
    )
    product.seller_requirements = requirements
    product.status = "listed"
    emit_swarm_step(
        run_id=run.run_id,
        role="merchant",
        phase="listing",
        action="build_seller_requirements",
        detail={
            "product_id": product.product_id,
            "price_usdc": product.price_usdc,
            "pay_to": requirements.get("pay_to"),
        },
    )
    return product
