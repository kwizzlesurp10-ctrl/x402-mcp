"""QMA(2)-inspired dual-witness verification for the swarm ("Arthur & the Merlins").

Motivation: a single agent can hallucinate a plausible-but-wrong answer with
high confidence. QMA(2) — Quantum Merlin-Arthur with *two isolated provers* —
gives the intuition for a cheap defense: have TWO specialists derive the answer
independently (no shared context, no cross-talk), then let a verifier ("Arthur")
accept only what both witnesses independently corroborate, while penalizing
suspicious agreement that looks copied rather than independently derived.

This module implements Arthur as a DETERMINISTIC, inspectable verifier over two
``Witness`` objects — matching the repo's data-honesty convention (every number
is computed from declared inputs; no marketing figures). Witness *production* is
a pluggable ``WitnessProducer`` callable, so the two Merlins can be backed by
live LLM subagents (see ``llm_witness_producer`` for the isolated, temp-0.1
adapter) or by any deterministic analyzer. The core never makes network calls,
so it is fully unit-testable.

Isolation is structural: each producer is invoked with ONLY the original task
and its own role charter — never the other witness, never Arthur's state.

Public API:
    run_qma_verification(task, producer, ...) -> VerificationReport   # spawn + verify (+ iterate)
    arthur_verify(task, witness_a, witness_b, ...) -> VerificationReport   # verify existing witnesses
"""

from __future__ import annotations

import difflib
import inspect
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable, Sequence, Union

# ---------------------------------------------------------------------------
# Witness model — what each isolated Merlin returns.
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    """One assertion in a witness. ``critical`` claims drive accept/reject."""

    text: str
    kind: str = "critical"  # "critical" | "supporting"
    evidence: str = ""  # citation / source backing the claim


@dataclass
class MerlinSpec:
    """Identity + charter for one isolated specialist (passed to the producer)."""

    agent_id: str
    role: str  # short name, e.g. "Optimistic Explorer"
    charter: str  # full persona / instruction for the witness producer
    temperature: float = 0.1  # honoured by the LLM adapter; 0.1 = truth-seeking


@dataclass
class Witness:
    """A complete, structured response from one isolated Merlin."""

    author_id: str
    reasoning_chain: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    kpis: dict[str, float] = field(default_factory=dict)
    failure_modes: list[str] = field(default_factory=list)
    raw: str = ""  # optional full text, for the entanglement (lexical) check

    def critical_claims(self) -> list[Claim]:
        return [c for c in self.claims if c.kind == "critical"]

    def reasoning_text(self) -> str:
        return self.raw or "\n".join(self.reasoning_chain)


# ---------------------------------------------------------------------------
# Verification report — Arthur's output (JSON-serialisable via to_dict()).
# ---------------------------------------------------------------------------


@dataclass
class VerificationReport:
    task: str
    verdict: str  # "accept" | "reject" | "iterate"
    accepted: bool
    rounds: int
    agreement_ratio: float  # 0..1 over union of critical claims
    entanglement_score: float  # 0..100; HIGH = suspiciously similar wording
    confidence: float  # 0..1
    soundness_ok: bool
    merged_solution: list[str] = field(default_factory=list)
    aligned_claims: list[str] = field(default_factory=list)
    single_witness_claims: list[dict[str, str]] = field(default_factory=list)
    contested_claims: list[str] = field(default_factory=list)
    kpis: dict[str, Any] = field(default_factory=dict)
    validation_steps: list[str] = field(default_factory=list)  # "edges"
    rollback_plan: list[str] = field(default_factory=list)
    witness_summaries: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Tunables (transparent; every threshold is inspectable).
# ---------------------------------------------------------------------------

# Two critical claims are "the same element" if their token-set (Jaccard)
# overlap meets this. Deliberately lenient — we cluster on topic, not wording.
CLAIM_MATCH_THRESHOLD = 0.5
# Accept only if witnesses align on >= this share of critical elements.
ACCEPTANCE_AGREEMENT = 0.80
# Above this entanglement, agreement looks copied, not independent → warn +
# dampen confidence (we do NOT hard-reject on entanglement alone).
ENTANGLEMENT_SUSPICIOUS = 70.0
# Modelled single-agent error rate for the corroboration KPI. Two INDEPENDENT
# witnesses agreeing drops joint error toward p²; stated as an assumption, not
# a measured fact.
DEFAULT_SINGLE_AGENT_ERROR_RATE = 0.30

_STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "is", "are", "be", "in", "on",
    "for", "with", "that", "this", "it", "as", "by", "will", "can", "we", "our",
    "you", "your", "at", "from", "if", "then", "than", "so", "but", "not", "no",
}
_NEGATIONS = {
    "not", "no", "never", "cannot", "can't", "won't", "shouldn't", "avoid",
    "reject", "fails", "fail", "unsafe", "insecure", "invalid", "without",
}

Validator = Callable[[str], bool]
WitnessProducer = Callable[[str, MerlinSpec], Union[Witness, Awaitable[Witness]]]

DEFAULT_SPECS: tuple[MerlinSpec, MerlinSpec] = (
    MerlinSpec(
        agent_id="Merlin-1",
        role="Optimistic Explorer",
        charter=(
            "Generate creative, forward-leaning solutions. List every assumption "
            "explicitly. Cite evidence for each critical claim. Report KPIs and "
            "the failure modes you can foresee."
        ),
    ),
    MerlinSpec(
        agent_id="Merlin-2",
        role="Skeptical Auditor",
        charter=(
            "Focus on risks, edge cases, counterarguments, and quantitative "
            "validation. Cite evidence for each critical claim. Report KPIs and "
            "the failure modes an optimist would miss."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Text helpers (stdlib only, deterministic).
# ---------------------------------------------------------------------------


def _stem(tok: str) -> str:
    """Trivial plural stemmer: keys→key, settlements→settlement (not success)."""
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _tokens(text: str) -> list[str]:
    """Content tokens for TOPIC matching — stopwords dropped, lightly stemmed.

    Polarity words ("not"/"no") are stopwords here on purpose: "safe" and "not
    safe" must cluster on the same topic so a contradiction is detected as a
    contested group rather than two unrelated claims.
    """
    return [
        _stem(t)
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if t not in _STOPWORDS
    ]


def _raw_tokens(text: str) -> list[str]:
    """Unfiltered tokens (keeps negations/apostrophes) for polarity detection."""
    return re.findall(r"[a-z0-9']+", text.lower())


def _token_set_ratio(a: str, b: str) -> float:
    """Jaccard over content tokens — topic overlap, order-insensitive."""
    sa, sb = set(_tokens(a)), set(_tokens(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _lexical_similarity(a: str, b: str) -> float:
    """Order-sensitive character-level similarity — catches copied wording."""
    if not a and not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _has_negation(text: str) -> bool:
    return any(t in _NEGATIONS for t in _raw_tokens(text))


# ---------------------------------------------------------------------------
# Arthur's verification math.
# ---------------------------------------------------------------------------


def _cluster_critical_claims(
    witness_a: Witness, witness_b: Witness
) -> list[dict[str, Any]]:
    """Group both witnesses' critical claims into shared 'elements'.

    A group aligned by BOTH authors (and not internally contradictory) is an
    independently corroborated element. Contradiction = same topic, opposite
    polarity (one negates what the other asserts).
    """
    tagged: list[tuple[str, Claim]] = [
        (witness_a.author_id, c) for c in witness_a.critical_claims()
    ] + [(witness_b.author_id, c) for c in witness_b.critical_claims()]

    groups: list[dict[str, Any]] = []
    for author, claim in tagged:
        for g in groups:
            if _token_set_ratio(claim.text, g["claims"][0][1].text) >= CLAIM_MATCH_THRESHOLD:
                g["claims"].append((author, claim))
                g["authors"].add(author)
                break
        else:
            groups.append({"claims": [(author, claim)], "authors": {author}})

    for g in groups:
        polarities = {_has_negation(c.text) for _, c in g["claims"]}
        # Contested only if authors genuinely disagree on polarity of a shared topic.
        g["contested"] = len(g["authors"]) > 1 and len(polarities) > 1
    return groups


def _entanglement_score(witness_a: Witness, witness_b: Witness) -> float:
    """0..100. HIGH = the two 'independent' outputs are suspiciously similar.

    Blends lexical similarity of the reasoning (copied wording) with verbatim
    evidence overlap. Independent agreement should show matching *conclusions*
    but distinct *wording/sources* — that lands LOW here, as it should.
    """
    lexical = _lexical_similarity(
        witness_a.reasoning_text(), witness_b.reasoning_text()
    )
    ev_a = {c.evidence.strip().lower() for c in witness_a.claims if c.evidence.strip()}
    ev_b = {c.evidence.strip().lower() for c in witness_b.claims if c.evidence.strip()}
    evidence_overlap = len(ev_a & ev_b) / len(ev_a | ev_b) if (ev_a or ev_b) else 0.0
    return round(100.0 * (0.7 * lexical + 0.3 * evidence_overlap), 1)


def arthur_verify(
    task: str,
    witness_a: Witness,
    witness_b: Witness,
    *,
    rounds: int = 1,
    validators: Sequence[Validator] = (),
    single_agent_error_rate: float = DEFAULT_SINGLE_AGENT_ERROR_RATE,
) -> VerificationReport:
    """Cross-validate two isolated witnesses and synthesise a verdict.

    Accept iff: aligned on >= 80% of critical elements (completeness) AND no
    corroborated claim is contested or fails a validator (soundness). High
    entanglement never *passes* a rejection but does dampen confidence and
    raises a warning — that is the "penalise suspicious similarity" rule.
    """
    groups = _cluster_critical_claims(witness_a, witness_b)
    both = {witness_a.author_id, witness_b.author_id}

    aligned = [g for g in groups if g["authors"] == both and not g["contested"]]
    contested = [g for g in groups if g["contested"]]
    single = [g for g in groups if len(g["authors"]) == 1]

    agreement_ratio = round(len(aligned) / len(groups), 3) if groups else 0.0
    entanglement = _entanglement_score(witness_a, witness_b)

    # Soundness: run caller validators over every corroborated (aligned) claim.
    unsound: list[str] = []
    for g in aligned:
        rep = g["claims"][0][1].text
        if any(not v(rep) for v in validators):
            unsound.append(rep)
    soundness_ok = not contested and not unsound

    # Confidence: agreement + soundness + independence (low entanglement).
    soundness_term = 1.0 if soundness_ok else (
        (len(aligned) - len(unsound)) / len(aligned) if aligned else 0.0
    )
    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.55 * agreement_ratio
                + 0.25 * soundness_term
                + 0.20 * (1.0 - entanglement / 100.0),
            ),
        ),
        3,
    )

    # Verdict per the protocol.
    if not soundness_ok:
        verdict = "reject"
    elif agreement_ratio >= ACCEPTANCE_AGREEMENT:
        verdict = "accept"
    else:
        verdict = "iterate"
    accepted = verdict == "accept"

    # Synthesis: the corroborated core is the merged solution.
    aligned_texts = [g["claims"][0][1].text for g in aligned]
    merged = list(aligned_texts)

    single_witness_claims = [
        {"author": next(iter(g["authors"])), "claim": g["claims"][0][1].text}
        for g in single
    ]
    contested_texts = [
        " || ".join(sorted({c.text for _, c in g["claims"]})) for g in contested
    ]

    # KPIs — computed from this run; the risk-reduction figure is MODELLED and
    # carries its assumption explicitly (no marketing numbers).
    corroboration = agreement_ratio
    union_failures = sorted(set(witness_a.failure_modes) | set(witness_b.failure_modes))
    kpis: dict[str, Any] = {
        "critical_elements": len(groups),
        "alignment_pct": round(agreement_ratio * 100.0, 1),
        "independent_corroboration_pct": round(corroboration * 100.0, 1),
        "failure_modes_identified": len(union_failures),
        "entanglement_score": entanglement,
        "confidence": confidence,
        "modeled_risk_reduction_pct": round(
            (1.0 - single_agent_error_rate) * corroboration * 100.0, 1
        ),
        "assumed_single_agent_error_rate": single_agent_error_rate,
        "modeling_note": (
            "risk reduction = (1 - assumed single-agent error rate) x share of "
            "critical claims independently corroborated by both isolated witnesses"
        ),
    }

    # Validation steps ("edges") — the concrete checks still owed.
    validation_steps: list[str] = []
    for g in contested:
        validation_steps.append(
            f"Resolve contradiction on: {g['claims'][0][1].text!r}"
        )
    for sc in single_witness_claims:
        validation_steps.append(
            f"Independently corroborate single-witness claim ({sc['author']}): "
            f"{sc['claim']!r}"
        )
    if entanglement >= ENTANGLEMENT_SUSPICIOUS:
        validation_steps.append(
            "Re-run Merlins with fresh seeds / different framings — high "
            f"entanglement ({entanglement}) suggests non-independent witnesses."
        )
    if agreement_ratio < ACCEPTANCE_AGREEMENT and not validation_steps:
        validation_steps.append(
            "Low completeness — iterate with additional witnesses before acting."
        )

    # Rollback plan — surfaced failure modes become guarded revert steps.
    rollback_plan = ["Revert to pre-decision state; act only on corroborated claims."]
    rollback_plan += [f"Mitigation for failure mode: {fm}" for fm in union_failures]

    notes: list[str] = []
    if entanglement >= ENTANGLEMENT_SUSPICIOUS:
        notes.append(
            f"WARNING: entanglement {entanglement} >= {ENTANGLEMENT_SUSPICIOUS} — "
            "agreement may be copied rather than independent; confidence dampened."
        )
    if not groups:
        notes.append("No critical claims supplied by either witness.")

    return VerificationReport(
        task=task,
        verdict=verdict,
        accepted=accepted,
        rounds=rounds,
        agreement_ratio=agreement_ratio,
        entanglement_score=entanglement,
        confidence=confidence,
        soundness_ok=soundness_ok,
        merged_solution=merged,
        aligned_claims=aligned_texts,
        single_witness_claims=single_witness_claims,
        contested_claims=contested_texts,
        kpis=kpis,
        validation_steps=validation_steps,
        rollback_plan=rollback_plan,
        witness_summaries=[
            {
                "author_id": w.author_id,
                "critical_claims": len(w.critical_claims()),
                "failure_modes": len(w.failure_modes),
                "kpis": w.kpis,
            }
            for w in (witness_a, witness_b)
        ],
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Driver: spawn two ISOLATED witnesses, verify, iterate on non-acceptance.
# ---------------------------------------------------------------------------


async def _produce(producer: WitnessProducer, task: str, spec: MerlinSpec) -> Witness:
    result = producer(task, spec)
    if inspect.isawaitable(result):
        result = await result
    return result


async def run_qma_verification(
    task: str,
    producer: WitnessProducer,
    *,
    specs: tuple[MerlinSpec, MerlinSpec] = DEFAULT_SPECS,
    max_rounds: int = 2,
    validators: Sequence[Validator] = (),
    single_agent_error_rate: float = DEFAULT_SINGLE_AGENT_ERROR_RATE,
) -> VerificationReport:
    """Run the full QMA(2) protocol and return Arthur's report.

    Spawns exactly two witnesses per round via ``producer``, each seeing ONLY
    ``task`` and its own ``MerlinSpec`` (isolation is enforced here — the
    producer is never handed the other witness). Verifies; if not accepted,
    re-derives with fresh witnesses up to ``max_rounds`` and returns the best
    report seen.
    """
    if len(specs) != 2:
        raise ValueError("QMA(2) requires exactly two Merlin specs.")

    best: VerificationReport | None = None
    for rnd in range(1, max_rounds + 1):
        witness_a = await _produce(producer, task, specs[0])
        witness_b = await _produce(producer, task, specs[1])
        report = arthur_verify(
            task,
            witness_a,
            witness_b,
            rounds=rnd,
            validators=validators,
            single_agent_error_rate=single_agent_error_rate,
        )
        if report.accepted:
            return report
        # Keep the most confident non-accepted report; ties favour the freshest
        # round (>=), so the returned report reflects the latest attempt.
        if best is None or report.confidence >= best.confidence:
            best = report
    assert best is not None  # loop runs at least once
    return best


# ---------------------------------------------------------------------------
# Optional live-LLM adapter (opt-in; NOT imported by the server path).
# ---------------------------------------------------------------------------


def llm_witness_producer(
    call_model: Callable[[str, float], str],
    parse: Callable[[str], Witness],
) -> WitnessProducer:
    """Build a WitnessProducer backed by a live model.

    ``call_model(prompt, temperature) -> raw_text`` is your provider call (e.g.
    a Claude subagent); ``parse(raw_text) -> Witness`` maps its structured reply
    to a Witness. The returned producer builds an isolated prompt from the task
    + the Merlin's charter, runs at the spec temperature (0.1 by default), and
    never exposes one Merlin's output to the other. Deliberately a thin seam so
    the network/LLM dependency stays out of the deterministic core and tests.
    """

    def _producer(task: str, spec: MerlinSpec) -> Witness:
        prompt = (
            f"ROLE: {spec.role} ({spec.agent_id})\n"
            f"CHARTER: {spec.charter}\n\n"
            f"TASK: {task}\n\n"
            "Work in isolation. Output a structured witness: reasoning chain, "
            "critical claims (each with an evidence citation), KPIs, and failure "
            "modes. Prioritise truth-seeking over agreement."
        )
        witness = parse(call_model(prompt, spec.temperature))
        witness.author_id = spec.agent_id
        return witness

    return _producer
