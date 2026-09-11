from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .continuity import ContinuationPacket
from .fabric_routing import constraints_require_local
from .provider_fabric import ExecutionFabric


class CouncilError(RuntimeError):
    pass


class CouncilMode(StrEnum):
    PARALLEL_REVIEW = "parallel-review"
    DEBATE = "debate"


class CouncilVerdict(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CONDITIONAL = "conditional"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class CouncilParticipant:
    role: str
    fabric: ExecutionFabric
    model: str
    local: bool | None = None
    alternates: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return f"{self.role}:{self.fabric.name}:{self.model}"

    @property
    def is_local(self) -> bool:
        if self.local is not None:
            return self.local
        return self.fabric.name == "ypipe"


@dataclass(frozen=True)
class CouncilOpinion:
    participant_id: str
    role: str
    fabric: str
    model: str
    round: int
    verdict: CouncilVerdict
    recommendation: str
    reasoning: str
    risks: tuple[str, ...]
    evidence: tuple[str, ...]
    conflicts: tuple[str, ...]
    confidence: float
    project_id: str
    state_version: int


@dataclass(frozen=True)
class CouncilFailure:
    participant_id: str
    role: str
    fabric: str
    model: str
    round: int
    error: str


@dataclass(frozen=True)
class CouncilResult:
    project_id: str
    state_version: int
    question: str
    mode: CouncilMode
    opinions: tuple[CouncilOpinion, ...]
    failures: tuple[CouncilFailure, ...]
    consensus: str
    disagreements: tuple[str, ...]
    average_confidence: float
    evidence_coverage: float
    quorum_met: bool
    canonical_state_mutated: bool = False


def _json_object(text: str) -> dict:
    candidate = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise CouncilError("Council participant returned non-JSON output") from exc
    if not isinstance(value, dict):
        raise CouncilError("Council participant must return one JSON object")
    return value


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _infer_verdict(value: object, recommendation: str) -> CouncilVerdict:
    if isinstance(value, str):
        normalized = value.strip().lower().replace("_", "-")
        mapping = {
            "approve": CouncilVerdict.APPROVE,
            "approved": CouncilVerdict.APPROVE,
            "yes": CouncilVerdict.APPROVE,
            "proceed": CouncilVerdict.APPROVE,
            "reject": CouncilVerdict.REJECT,
            "rejected": CouncilVerdict.REJECT,
            "no": CouncilVerdict.REJECT,
            "conditional": CouncilVerdict.CONDITIONAL,
            "approve-with-conditions": CouncilVerdict.CONDITIONAL,
            "abstain": CouncilVerdict.ABSTAIN,
            "insufficient-evidence": CouncilVerdict.ABSTAIN,
        }
        if normalized in mapping:
            return mapping[normalized]
    text = recommendation.strip().lower()
    if any(token in text for token in ("do not", "don't", "reject", "avoid", "block")):
        return CouncilVerdict.REJECT
    if any(token in text for token in ("if ", "only if", "with condition", "conditional", "provided that")):
        return CouncilVerdict.CONDITIONAL
    if any(token in text for token in ("insufficient", "cannot determine", "abstain", "need more evidence")):
        return CouncilVerdict.ABSTAIN
    if any(token in text for token in ("approve", "proceed", "go ahead", "ship", "yes")):
        return CouncilVerdict.APPROVE
    return CouncilVerdict.CONDITIONAL


def _opinion_from_payload(
    *,
    payload: dict,
    participant: CouncilParticipant,
    packet: ContinuationPacket,
    round_number: int,
) -> CouncilOpinion:
    project_id = payload.get("everstate_project_id")
    state_version = payload.get("everstate_state_version")
    if project_id != packet.project_id or state_version != packet.state_version:
        raise CouncilError(
            f"Council identity drift from {participant.id}: expected "
            f"{packet.project_id}@{packet.state_version}, got {project_id!r}@{state_version!r}"
        )
    recommendation = payload.get("recommendation")
    reasoning = payload.get("reasoning")
    if not isinstance(recommendation, str) or not recommendation.strip():
        raise CouncilError(f"Council participant {participant.id} omitted recommendation")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise CouncilError(f"Council participant {participant.id} omitted reasoning")
    confidence_raw = payload.get("confidence", 0.5)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    return CouncilOpinion(
        participant_id=participant.id,
        role=participant.role,
        fabric=participant.fabric.name,
        model=participant.model,
        round=round_number,
        verdict=_infer_verdict(payload.get("verdict"), recommendation),
        recommendation=recommendation.strip(),
        reasoning=reasoning.strip(),
        risks=_string_list(payload.get("risks")),
        evidence=_string_list(payload.get("evidence")),
        conflicts=_string_list(payload.get("conflicts")),
        confidence=confidence,
        project_id=packet.project_id,
        state_version=packet.state_version,
    )


def _messages(
    *,
    packet: ContinuationPacket,
    question: str,
    participant: CouncilParticipant,
    round_number: int,
    prior_opinions: Iterable[CouncilOpinion] = (),
) -> list[dict]:
    prior = list(prior_opinions)
    system = (
        "You are an advisory agent inside Everstate AgentCouncil. Everstate is the sole canonical state authority. "
        "You may advise, critique, or request evidence, but you MUST NOT claim to mutate canonical state. "
        "Repository evidence outranks stale summaries. Preserve all active constraints. Return JSON only with keys: "
        "everstate_project_id, everstate_state_version, verdict, recommendation, reasoning, risks, evidence, conflicts, confidence. "
        "verdict must be one of: approve, reject, conditional, abstain. Use abstain when evidence is insufficient."
    )
    user_parts = [
        packet.to_prompt(),
        "",
        f"COUNCIL ROLE: {participant.role}",
        f"COUNCIL ROUND: {round_number}",
        f"QUESTION: {question}",
    ]
    if prior:
        user_parts.extend(["", "PRIOR COUNCIL OPINIONS TO CRITIQUE:"])
        for opinion in prior:
            user_parts.append(
                json.dumps(
                    {
                        "participant": opinion.participant_id,
                        "verdict": opinion.verdict.value,
                        "recommendation": opinion.recommendation,
                        "reasoning": opinion.reasoning,
                        "risks": list(opinion.risks),
                        "evidence": list(opinion.evidence),
                        "conflicts": list(opinion.conflicts),
                        "confidence": opinion.confidence,
                    },
                    ensure_ascii=False,
                )
            )
    user_parts.append(
        "Respond independently. Explicitly surface disagreement, missing evidence, and constraint conflicts."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def _retryable_participant_error(exc: Exception) -> bool:
    text = str(exc).casefold()
    if "identity drift" in text:
        return False
    if isinstance(exc, TimeoutError):
        return True
    markers = (
        "http 429",
        "rate_limit",
        "rate limit",
        "rate-limited",
        "cooldown",
        "all models exhausted",
        "model_not_found",
        "model not found",
        "http 404",
        "timeout",
        "timed out",
        "non-json output",
        "must return one json object",
        "omitted recommendation",
        "omitted reasoning",
        "schema",
        "malformed",
    )
    if any(marker in text for marker in markers):
        return True
    return re.search(r"http 5\d\d", text) is not None


def _execute_one(
    participant: CouncilParticipant,
    packet: ContinuationPacket,
    question: str,
    round_number: int,
    prior_opinions: Iterable[CouncilOpinion],
) -> CouncilOpinion:
    models = (participant.model, *participant.alternates[:4])
    failures: list[str] = []
    for index, model in enumerate(models):
        active = CouncilParticipant(
            role=participant.role,
            fabric=participant.fabric,
            model=model,
            local=participant.local,
        )
        try:
            response = active.fabric.execute(
                model=model,
                messages=_messages(
                    packet=packet,
                    question=question,
                    participant=active,
                    round_number=round_number,
                    prior_opinions=prior_opinions,
                ),
            )
            return _opinion_from_payload(
                payload=_json_object(response.content),
                participant=active,
                packet=packet,
                round_number=round_number,
            )
        except Exception as exc:  # noqa: BLE001 - classify provider/schema failures centrally
            if not _retryable_participant_error(exc):
                raise
            failures.append(f"{model}: {str(exc)[:300]}")
            if index == len(models) - 1:
                break
    raise CouncilError(
        f"Council participant {participant.role}:{participant.fabric.name} exhausted bounded model failover: "
        + " | ".join(failures)
    )


def _parallel_round(
    participants: tuple[CouncilParticipant, ...],
    packet: ContinuationPacket,
    question: str,
    round_number: int,
    prior_opinions: tuple[CouncilOpinion, ...],
) -> tuple[tuple[CouncilOpinion, ...], tuple[CouncilFailure, ...]]:
    if not participants:
        raise CouncilError("AgentCouncil requires at least one participant")
    results: list[CouncilOpinion] = []
    failures: list[CouncilFailure] = []
    with ThreadPoolExecutor(max_workers=min(8, len(participants))) as pool:
        futures = {
            pool.submit(_execute_one, participant, packet, question, round_number, prior_opinions): participant
            for participant in participants
        }
        for future in as_completed(futures):
            participant = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - isolate participant failure and preserve identity
                failures.append(
                    CouncilFailure(
                        participant_id=participant.id,
                        role=participant.role,
                        fabric=participant.fabric.name,
                        model=participant.model,
                        round=round_number,
                        error=str(exc)[:500],
                    )
                )
    results.sort(key=lambda item: item.participant_id)
    failures.sort(key=lambda item: item.participant_id)
    return tuple(results), tuple(failures)


def _quorum_error(round_number: int, succeeded: int, quorum: int, failures: tuple[CouncilFailure, ...]) -> CouncilError:
    detail = "; ".join(f"{failure.participant_id}: {failure.error}" for failure in failures)
    suffix = f"; failures: {detail}" if detail else ""
    return CouncilError(
        f"AgentCouncil quorum not met in round {round_number}: {succeeded}/{quorum} successful{suffix}"
    )


def _synthesize(opinions: tuple[CouncilOpinion, ...]) -> tuple[str, tuple[str, ...], float, float]:
    if not opinions:
        return "NO_OPINIONS", (), 0.0, 0.0
    voting = [opinion for opinion in opinions if opinion.verdict is not CouncilVerdict.ABSTAIN]
    average_confidence = sum(opinion.confidence for opinion in opinions) / len(opinions)
    evidence_coverage = sum(1 for opinion in opinions if opinion.evidence) / len(opinions)
    if not voting:
        return "NO_CONSENSUS: all participants abstained", (), average_confidence, evidence_coverage
    counts: dict[CouncilVerdict, int] = {}
    for opinion in voting:
        counts[opinion.verdict] = counts.get(opinion.verdict, 0) + 1
    best, best_count = max(counts.items(), key=lambda row: (row[1], row[0].value))
    if best_count == len(voting):
        label = f"CONSENSUS: {best.value}"
    elif best_count > len(voting) / 2:
        label = f"MAJORITY: {best.value}"
    else:
        label = "NO_CONSENSUS"
    disagreements = tuple(
        sorted(
            {
                f"{opinion.participant_id}: {opinion.verdict.value} — {opinion.recommendation}"
                for opinion in opinions
                if opinion.verdict is CouncilVerdict.ABSTAIN or opinion.verdict is not best
            }
        )
    )
    return label, disagreements, average_confidence, evidence_coverage


def execute_agent_council(
    *,
    packet: ContinuationPacket,
    question: str,
    participants: Iterable[CouncilParticipant],
    mode: CouncilMode = CouncilMode.PARALLEL_REVIEW,
    rounds: int = 2,
    min_successful: int | None = None,
) -> CouncilResult:
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question must not be empty")
    participant_tuple = tuple(participants)
    if not participant_tuple:
        raise CouncilError("AgentCouncil requires at least one participant")
    if rounds < 1 or rounds > 5:
        raise ValueError("rounds must be between 1 and 5")
    ids = [participant.id for participant in participant_tuple]
    if len(ids) != len(set(ids)):
        raise CouncilError("AgentCouncil participants must have unique role/fabric/model identities")
    if constraints_require_local(packet.constraints):
        remote = [participant.id for participant in participant_tuple if not participant.is_local]
        if remote:
            raise CouncilError(
                "Canonical constraints require local execution; remote council participants are forbidden: "
                + ", ".join(remote)
            )
    quorum = min_successful if min_successful is not None else math.floor(len(participant_tuple) / 2) + 1
    if quorum < 1 or quorum > len(participant_tuple):
        raise ValueError("min_successful must be between 1 and the participant count")

    first, first_failures = _parallel_round(participant_tuple, packet, clean_question, 1, ())
    if len(first) < quorum:
        raise _quorum_error(1, len(first), quorum, first_failures)
    all_opinions = list(first)
    all_failures = list(first_failures)
    if mode is CouncilMode.DEBATE:
        prior = first
        for round_number in range(2, rounds + 1):
            current, failures = _parallel_round(participant_tuple, packet, clean_question, round_number, prior)
            all_failures.extend(failures)
            if len(current) < quorum:
                raise _quorum_error(round_number, len(current), quorum, failures)
            all_opinions.extend(current)
            prior = current

    final_round_number = max(opinion.round for opinion in all_opinions)
    final_round = tuple(opinion for opinion in all_opinions if opinion.round == final_round_number)
    consensus, disagreements, average_confidence, evidence_coverage = _synthesize(final_round)
    return CouncilResult(
        project_id=packet.project_id,
        state_version=packet.state_version,
        question=clean_question,
        mode=mode,
        opinions=tuple(all_opinions),
        failures=tuple(all_failures),
        consensus=consensus,
        disagreements=disagreements,
        average_confidence=average_confidence,
        evidence_coverage=evidence_coverage,
        quorum_met=True,
        canonical_state_mutated=False,
    )
