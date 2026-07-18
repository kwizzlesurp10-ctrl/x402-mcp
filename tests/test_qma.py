"""QMA(2) dual-witness verification ("Arthur & the Merlins").

Deterministic core — no network, no LLM. Fake producers stand in for the two
isolated Merlins so every assertion is reproducible.
"""

from __future__ import annotations

import pytest

from app.swarm import qma
from app.swarm.qma import Claim, MerlinSpec, Witness


def _w(author: str, claims, *, reasoning="", failure_modes=None, kpis=None) -> Witness:
    return Witness(
        author_id=author,
        reasoning_chain=[reasoning] if reasoning else [],
        claims=[Claim(**c) if isinstance(c, dict) else c for c in claims],
        kpis=kpis or {},
        failure_modes=failure_modes or [],
        raw=reasoning,
    )


def test_full_agreement_independent_wording_accepts():
    a = _w(
        "Merlin-1",
        [
            {"text": "Use idempotency keys to dedupe settlement", "evidence": "src-A1"},
            {"text": "Cap spend per call at policy limit", "evidence": "src-A2"},
        ],
        reasoning="An explorer's optimistic derivation of the settlement design.",
    )
    b = _w(
        "Merlin-2",
        [
            {"text": "Dedupe settlements via idempotency key", "evidence": "src-B1"},
            {"text": "Per-call spend must respect the policy cap", "evidence": "src-B2"},
        ],
        reasoning="A skeptic audits caps and replay risk with different words.",
    )
    r = qma.arthur_verify("design safe settlement", a, b)
    assert r.accepted is True
    assert r.verdict == "accept"
    assert r.agreement_ratio >= qma.ACCEPTANCE_AGREEMENT
    assert r.entanglement_score < qma.ENTANGLEMENT_SUSPICIOUS
    assert len(r.merged_solution) == 2
    assert r.confidence > 0.5


def test_contradiction_blocks_acceptance():
    a = _w("Merlin-1", [{"text": "The migration is safe to run now", "evidence": "x"}])
    b = _w("Merlin-1".replace("1", "2"),
           [{"text": "The migration is not safe to run now", "evidence": "y"}])
    r = qma.arthur_verify("ship migration?", a, b)
    assert r.soundness_ok is False
    assert r.verdict == "reject"
    assert r.contested_claims  # the disagreement is surfaced


def test_low_completeness_iterates():
    a = _w("Merlin-1", [
        {"text": "Alpha claim about caching"},
        {"text": "Beta claim about retries"},
    ])
    b = _w("Merlin-2", [
        {"text": "Alpha claim about caching"},  # only one of two aligns
        {"text": "Gamma claim about sharding"},
    ])
    r = qma.arthur_verify("plan", a, b)
    assert r.agreement_ratio < qma.ACCEPTANCE_AGREEMENT
    assert r.verdict == "iterate"
    assert r.accepted is False
    assert r.single_witness_claims  # unmatched claims flagged for corroboration


def test_high_entanglement_penalises_confidence_and_warns():
    text = "Exactly the same reasoning, verbatim, word for word, identical output."
    shared = [{"text": "Adopt the plan as written", "evidence": "same-source"}]
    a = _w("Merlin-1", list(shared), reasoning=text)
    b = _w("Merlin-2", list(shared), reasoning=text)
    r = qma.arthur_verify("adopt plan?", a, b)
    assert r.entanglement_score >= qma.ENTANGLEMENT_SUSPICIOUS
    assert any("entanglement" in n.lower() for n in r.notes)
    # Same claims but independent wording would score higher confidence; here it's damped.
    assert any("fresh seeds" in s.lower() for s in r.validation_steps)


def test_validator_failure_is_unsound():
    a = _w("Merlin-1", [{"text": "The API returns 200 on success", "evidence": "e1"}])
    b = _w("Merlin-2", [{"text": "The API returns 200 on a successful call", "evidence": "e2"}])
    # Aligned on topic, but a cross-validator refutes the claim → reject.
    r = qma.arthur_verify("verify api", a, b, validators=[lambda _text: False])
    assert r.soundness_ok is False
    assert r.verdict == "reject"


def test_kpis_are_computed_and_assumption_is_explicit():
    a = _w("Merlin-1", [{"text": "claim one", "evidence": "e"}],
           failure_modes=["timeout under load"])
    b = _w("Merlin-2", [{"text": "claim one restated", "evidence": "f"}],
           failure_modes=["timeout under load", "key leak"])
    r = qma.arthur_verify("t", a, b)
    assert r.kpis["critical_elements"] == 1
    assert r.kpis["independent_corroboration_pct"] == 100.0
    assert r.kpis["failure_modes_identified"] == 2  # union, deduped
    assert r.kpis["assumed_single_agent_error_rate"] == qma.DEFAULT_SINGLE_AGENT_ERROR_RATE
    assert "modeling_note" in r.kpis
    # rollback plan folds in every surfaced failure mode
    assert any("timeout under load" in step for step in r.rollback_plan)
    assert r.to_dict()["verdict"] == r.verdict  # serialisable


@pytest.mark.asyncio
async def test_run_qma_isolation_and_acceptance():
    seen_specs: list[str] = []

    def producer(task: str, spec: MerlinSpec) -> Witness:
        # Producer only ever sees task + its own spec — never the other witness.
        seen_specs.append(spec.agent_id)
        return _w(spec.agent_id, [{"text": "shared conclusion", "evidence": spec.agent_id}],
                  reasoning=f"{spec.role} reasons uniquely about {task}")

    r = await qma.run_qma_verification("design X", producer)
    assert r.accepted is True
    assert seen_specs == ["Merlin-1", "Merlin-2"]  # exactly two, in order, one round


@pytest.mark.asyncio
async def test_run_qma_iterates_then_returns_best():
    rounds_run = {"n": 0}

    def producer(task: str, spec: MerlinSpec) -> Witness:
        rounds_run["n"] += 1
        # Never aligns → forces iteration to max_rounds.
        uniq = f"{spec.agent_id}-r{rounds_run['n']}"
        return _w(spec.agent_id, [{"text": f"distinct claim {uniq}"}])

    r = await qma.run_qma_verification("x", producer, max_rounds=3)
    assert r.accepted is False
    assert r.rounds == 3  # returned the last/best round
    assert rounds_run["n"] == 6  # two witnesses x three rounds


@pytest.mark.asyncio
async def test_run_qma_supports_async_producer():
    async def producer(task: str, spec: MerlinSpec) -> Witness:
        return _w(spec.agent_id, [{"text": "same", "evidence": spec.agent_id}],
                  reasoning=f"{spec.agent_id} unique text")

    r = await qma.run_qma_verification("x", producer)
    assert r.accepted is True


def test_requires_exactly_two_specs():
    async def _run():
        await qma.run_qma_verification(
            "x", lambda t, s: _w(s.agent_id, []),
            specs=(qma.DEFAULT_SPECS[0],),  # only one
        )

    import asyncio

    with pytest.raises(ValueError, match="exactly two"):
        asyncio.run(_run())
