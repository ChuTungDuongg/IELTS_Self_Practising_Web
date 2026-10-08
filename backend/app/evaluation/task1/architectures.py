"""A0/A1/A2/A3 share production services; A4 is deliberately unimplemented."""

from app.domains.scoring.direct_writing_prompts import DIRECT_PROMPT_VERSION
from app.domains.scoring.tacs_prompts import PAIRWISE_PROMPT_VERSION
from app.evaluation.task1.anchor_sources import AnchorSource
from app.services.task1_tacs import FEEDBACK_PROMPT_VERSION, HYBRID_PROMPT_VERSION


def architecture_configurations(
    settings,
    architecture="anchor-pairwise",
    chart_specialist="off",
    *,
    scoring_version="v5",
    tree_node_budget=2,
    source=None,
):
    from app.evaluation.task1.runner import configurations

    if architecture not in {
        "direct",
        "mts",
        "direct-self-consistency",
        "anchor-pairwise",
        "all",
    } or tree_node_budget not in (1, 2, 3):
        raise ValueError("BENCHMARK_CONFIGURATION_INVALID")
    if architecture != "mts" and scoring_version != "v5":
        raise ValueError("BENCHMARK_SCORING_VERSION_IS_MTS_ONLY")
    source = source or AnchorSource()
    choices = (
        ["direct", "mts", "direct-self-consistency", "anchor-pairwise"]
        if architecture == "all"
        else [architecture]
    )
    configs = []
    for name in choices:
        for base in configurations(
            settings, scoring_version if name == "mts" else "v5", chart_specialist
        ):
            if name == "mts":
                configs.append(base.model_copy(update={"label": "A1 MTS · " + base.label}))
                continue
            aid = {"direct": "A0", "direct-self-consistency": "A2", "anchor-pairwise": "A3"}[name]
            hybrid = name == "anchor-pairwise"
            version = HYBRID_PROMPT_VERSION if hybrid else DIRECT_PROMPT_VERSION
            configs.append(
                base.model_copy(
                    update={
                        "architecture": name,
                        "architecture_id": aid,
                        "label": f"{aid} {name}:deplot-{'on' if base.specialist.enabled else 'off'}",
                        "prompt_version": version,
                        "scoring_prompt_version": version,
                        "tree_node_budget": tree_node_budget,
                        "self_consistency_count": 3 if name == "direct-self-consistency" else 1,
                        "anchor_digest": source.digest if hybrid else None,
                        "anchor_set_id": str(source.snapshot.id)
                        if hybrid and source.snapshot.id
                        else None,
                        "anchor_set_version": source.snapshot.version if hybrid else None,
                        "anchor_density": source.density if hybrid else {},
                        "pairwise_prompt_version": PAIRWISE_PROMPT_VERSION if hybrid else None,
                        "feedback_prompt_version": FEEDBACK_PROMPT_VERSION if hybrid else None,
                    }
                )
            )
    return configs
