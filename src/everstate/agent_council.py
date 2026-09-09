from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .continuity import ContinuationPacket
from .provider_fabric import ExecutionFabric


class CouncilError(RuntimeError):
    pass


class CouncilMode(StrEnum):
    PARALLEL_REVIEW = "parallel-review"
    DEBATE = "debate"


@dataclass(frozen=True)
class CouncilParticipant:
    role: str
    fabric: ExecutionFabric
    model: str

    @property
    def id(self) -> str:
        return f"{self.role}:{self.fabric.name}:{self.model}"


@dataclass(frozen=True)
class CouncilOpinion:
    participant_id: str
    role: str
    fabric: str
    model: str
    round: int
    recommendation: str
    reasoning: str
    risks: tuple[str, ...]
    evidence: tuple[str, ...]
    conflicts: tuple[str, ...]
    confidence: float
    project_id: str
    state_version: int


@dataclass(frozen=True)
class CouncilResult:
    project_id: str
    state_version: int
    question: str
    mode: CouncilMode
    opinions: tuple[CouncilOpinion, ...]
    consensus: str
    disagreements: tuple[str, ...]
    average_confidence: float
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
        "everstate_project_id, everstate_state_version, recommendation, reasoning, risks, evidence, conflicts, confidence."
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
                        "recommendation": opinion.recommendation,
                        "reasoning": opinion.reasoning,
                        "risks": list(opinion.risks),
                        "conflicts": list(opinion.conflicts),
                        "confidence": opinion.confidence,
                    },
                    ensure_ascii=False,
                )
            )
    user_parts.append(
        "Respond as an independent reviewer. Explicitly surface disagreement, missing evidence, and constraint conflicts."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def _execute_one(
    participant: CouncilParticipant,
    packet: ContinuationPacket,
    question: str,
    round_number: int,
    prior_opinions: Iterable[CouncilOpinion],
) -> CouncilOpinion:
    response = participant.fabric.execute(
        model=participant.model,
        messages=_messages(
            packet=packet,
            question=question,
            participant=participant,
            round_number=round_number,
            prior_opinions=prior_opinions,
        ),
    )
    return _opinion_from_payload(
        payload=_json_object(response.content),
        participant=participant,
        packet=packet,
        round_number=round_number,
    )


def _parallel_round(
    participants: tuple[CouncilParticipant, ...],
    packet: ContinuationPacket,
    question: str,
    round_number: int,
    prior_opinions: tuple[CouncilOpinion, ...],
) -> tuple[CouncilOpinion, ...]:
    if not participants:
        raise CouncilError("AgentCouncil requires at least one participant")
    results: list[CouncilOpinion] = []
    with ThreadPoolExecutor(max_workers=min(8, len(participants))) as pool:
        futures = {
            pool.submit(_execute_one, participant, packet, question, round_number, prior_opinions): participant
            for participant in participants
        }
        for future in as_completed(futures):
            participant = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - preserve participant identity in aggregate failure
                raise CouncilError(f"Council participant failed: {participant.id}: {exc}") from exc
    results.sort(key=lambda item: item.participant_id)
    return tuple(results)


def _synthesize(opinions: tuple[CouncilOpinion, ...]) -> tuple[str, tuple[str, ...], float]:
    if not opinions:
        return "NO_OPINIONS", (), 0.0
    normalized = [opinion.recommendation.strip().lower() for opinion in opinions]
    counts: dict[str, int] = {}
    for value in normalized:
        counts[value] = counts.get(value, 0) + 1
    best, best_count = max(counts.items(), key=lambda row: (row[1], row[0]))
    consensus = next(
        opinion.recommendation for opinion in opinions if opinion.recommendation.strip().lower() == best
    )
    if best_count == len(opinions):
        label = f"CONSENSUS: {consensus}"
    elif best_count > len(opinions) / 2:
        label = f"MAJORITY: {consensus}"
    else:
        label = "NO_CONSENSUS"
    disagreements = tuple(
        sorted(
            {
                f"{opinion.participant_id}: {opinion.recommendation}"
                for opinion in opinions
                if opinion.recommendation.strip().lower() != best
            }
        )
    )
    average_confidence = sum(opinion.confidence for opinion in opinions) / len(opinions)
    return label, disagreements, average_confidence


def execute_agent_council(
    *,
    packet: ContinuationPacket,
    question: str,
    participants: Iterable[CouncilParticipant],
    mode: CouncilMode = CouncilMode.PARALLEL_REVIEW,
    rounds: int = 2,
) -> CouncilResult:
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("question must not be empty")
    participant_tuple = tuple(participants)
    if not participant_tuple:
        raise CouncilError("AgentCouncil requires at least one participant")
    if rounds < 1 or rounds > 5:
        raise ValueError("rounds must be between 1 and 5")

    first = _parallel_round(participant_tuple, packet, clean_question, 1, ())
    all_opinions = list(first)
    if mode is CouncilMode.DEBATE:
        prior = first
        for round_number in range(2, rounds + 1):
            current = _parallel_round(participant_tuple, packet, clean_question, round_number, prior)
            all_opinions.extend(current)
            prior = current

    final_round = tuple(opinion for opinion in all_opinions if opinion.round == max(o.round for o in all_opinions))
    consensus, disagreements, average_confidence = _synthesize(final_round)
    return CouncilResult(
        project_id=packet.project_id,
        state_version=packet.state_version,
        question=clean_question,
        mode=mode,
        opinions=tuple(all_opinions),
        consensus=consensus,
        disagreements=disagreements,
        average_confidence=average_confidence,
        canonical_state_mutated=False,
    )
