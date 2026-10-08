"""Conservative verification against structured observations, never score penalties."""

from app.domains.scoring.task1_facts import DerivedFact
from app.schemas.task1_claims import (
    ComparisonCheck,
    ExtractedClaim,
    NumericCheck,
    RelationCheck,
    Verdict,
)
from app.schemas.task1_visual import (
    MapVisualReference,
    ProcessVisualReference,
    SystemVisualReference,
    VisualReference,
)


def _same(left: str | None, right: str | None) -> bool:
    return (
        left is not None
        and right is not None
        and left.casefold().strip() == right.casefold().strip()
    )


def _relation(check: RelationCheck, reference: VisualReference) -> bool | None:
    if isinstance(reference, ProcessVisualReference):
        subjects = [stage.id for stage in reference.stages if _same(stage.label, check.subject)]
        others = [stage.id for stage in reference.stages if _same(stage.label, check.other)]
        if len(subjects) != 1:
            return None
        if check.relation == "stage":
            return True
        if check.relation != "before" or len(others) != 1:
            return None

        def reaches(start: str, end: str) -> bool:
            seen, pending = set(), [start]
            while pending:
                current = pending.pop()
                if current == end:
                    return True
                if current in seen:
                    continue
                seen.add(current)
                pending.extend(edge.target for edge in reference.edges if edge.source == current)
            return False

        forward, backward = reaches(subjects[0], others[0]), reaches(others[0], subjects[0])
        return True if forward and not backward else False if backward and not forward else None
    if isinstance(reference, SystemVisualReference) and check.relation == "connected":
        left = [item.id for item in reference.components if _same(item.label, check.subject)]
        right = [item.id for item in reference.components if _same(item.label, check.other)]
        if len(left) != 1 or len(right) != 1:
            return None
        if any(
            edge.source == left[0] and edge.target == right[0] for edge in reference.connections
        ):
            return True
        # Absent edges do not prove absence; a clearly reversed directed edge does.
        return (
            False
            if any(
                edge.source == right[0] and edge.target == left[0] for edge in reference.connections
            )
            else None
        )
    if isinstance(reference, MapVisualReference):
        states = {state.id: state for state in reference.states}
        for change in reference.changes:
            before, after = states[change.from_state], states[change.to_state]
            if not _same(check.from_state, before.label) or not _same(check.to_state, after.label):
                continue
            old = next((item for item in before.features if item.id == change.before), None)
            new = next((item for item in after.features if item.id == change.after), None)
            subject = new if check.relation == "addition" else old
            if subject and _same(check.subject, subject.label):
                if change.kind != check.relation:
                    continue
                if check.relation == "replacement" and (
                    not new or not _same(check.other, new.label)
                ):
                    return False if new is not None else None
                return True if check.location is None or check.location == change.location else None
        if check.relation == "location" and check.to_state:
            features = [
                feature
                for state in reference.states
                if _same(state.label, check.to_state)
                for feature in state.features
                if _same(feature.label, check.subject)
            ]
            if len(features) == 1 and features[0].location != "unspecified":
                return features[0].location == check.location
    return None


def verify_claim(
    claim: ExtractedClaim, reference: VisualReference, facts: list[DerivedFact]
) -> tuple[Verdict, str, list[str]]:
    check = claim.check
    if check is None or reference.confidence not in {"HIGH", "MEDIUM"}:
        return (
            "INSUFFICIENT_EVIDENCE",
            "Chưa đủ dữ liệu đáng tin cậy để đối chiếu nhận định này.",
            [],
        )
    outcome: bool | None = None
    evidence: list[str] = []
    if isinstance(check, NumericCheck):
        matching = [
            fact
            for fact in facts
            if fact.kind == check.fact
            and (check.component_id is None or fact.component_id == check.component_id)
            and any(_same(subject, check.subject) for subject in fact.subjects)
            and (check.category is None or _same(fact.category, check.category))
            and (check.end_category is None or _same(fact.end_category, check.end_category))
        ]
        # Missing category for point/rank assertions is ambiguous, even if values happen to agree.
        if check.fact in {"value", "rank"} and check.category is None:
            matching = []
        if len(matching) == 1:
            fact = matching[0]
            assertions = []
            if check.direction is not None:
                assertions.append(
                    fact.direction == check.direction if fact.direction is not None else None
                )
            if check.value is not None:
                assertions.append(fact.value == check.value if fact.value is not None else None)
            if assertions and all(item is not None for item in assertions):
                outcome = all(assertions)
            evidence = [fact.id]
    elif isinstance(check, ComparisonCheck):
        left = [
            fact
            for fact in facts
            if fact.kind == "value"
            and _same(fact.subjects[0], check.subject)
            and _same(fact.category, check.category)
            and (check.component_id is None or fact.component_id == check.component_id)
        ]
        right = [
            fact
            for fact in facts
            if fact.kind == "value"
            and _same(fact.subjects[0], check.other)
            and _same(fact.category, check.category)
            and (check.component_id is None or fact.component_id == check.component_id)
        ]
        if len(left) == len(right) == 1 and left[0].component_id == right[0].component_id:
            a, b = left[0].value, right[0].value
            outcome = {"gt": a > b, "lt": a < b, "eq": a == b}[check.operator]
            evidence = [left[0].id, right[0].id]
    elif isinstance(check, RelationCheck):
        outcome = _relation(check, reference)
    if outcome is None:
        return (
            "INSUFFICIENT_EVIDENCE",
            "Hình chưa cung cấp đủ dữ liệu rõ ràng để xác minh nhận định.",
            evidence,
        )
    return (
        ("SUPPORTED", "Nhận định phù hợp với thông tin đã đối chiếu từ hình.", evidence)
        if outcome
        else (
            "CONTRADICTED",
            "Nhận định chưa khớp với thông tin đáng tin cậy trong hình.",
            evidence,
        )
    )
