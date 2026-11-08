"""Pure release decision support over persisted evidence, never model inference."""

from statistics import mean

from app.evaluation.speaking.metrics import score_metrics
from app.services.speaking_benchmark_research_metrics import paired_difference

FIELDS = ("fc", "lr", "gra", "pr", "overall")
BINDINGS = (
    "source_sha256",
    "manifest_fingerprint",
    "review_revision",
    "label_fingerprint",
    "reference_fingerprint",
)
HIGHER_BETTER = {
    "filler_recall",
    "repetition_recall",
    "recognition_coverage",
    "exact_agreement",
    "within_0_5",
    "score_coverage",
    "cache_reuse_rate",
}


def _metric(row, sample, name):
    if row is None:
        return (
            1.0
            if name in {"failure_rate", "missing_overall_rate", "missing_artifact_count"}
            else 0.0
            if name == "score_coverage"
            else None
        )
    human, ai = sample.get("human", {}), row.get("ai", {})
    if name.endswith("_mae"):
        field = name[:-4]
        return (
            abs(ai[field] - human[field])
            if ai.get(field) is not None and human.get(field) is not None
            else None
        )
    if name in {"exact_agreement", "within_0_5", "signed_bias_abs"}:
        if ai.get("overall") is None or human.get("overall") is None:
            return None
        error = ai["overall"] - human["overall"]
        return (
            float(error == 0)
            if name == "exact_agreement"
            else float(abs(error) <= 0.5)
            if name == "within_0_5"
            else error
        )
    if name == "score_coverage":
        return float(ai.get("overall") is not None)
    if name == "missing_overall_rate":
        return float(ai.get("overall") is None)
    if name == "missing_artifact_count":
        return float(not row.get("available"))
    if name == "failure_rate":
        return row.get("metrics", {}).get(name, float(not row.get("available")))
    return row.get("metrics", {}).get(name)


def evaluate_regression(policy, suite, baseline, candidate, quality):
    samples = suite["samples"]
    left = {r["sample_id"]: r for r in baseline.get("rows", [])}
    right = {r["sample_id"]: r for r in candidate.get("rows", [])}
    invalid = list(baseline.get("invalid_reasons", [])) + list(candidate.get("invalid_reasons", []))
    failed, unavailable = [], []
    if len(left) != len(baseline.get("rows", [])) or len(right) != len(candidate.get("rows", [])):
        invalid.append("DUPLICATE_SAMPLE_ARTIFACT")
    for sample in samples:
        for row in (left.get(sample["sample_id"]), right.get(sample["sample_id"])):
            if row and any(row.get(k) != sample.get(k) for k in BINDINGS):
                invalid.append("SOURCE_REVIEW_OR_REFERENCE_INCOMPATIBLE")
    a_config, b_config = baseline.get("configuration", {}), candidate.get("configuration", {})
    for key in ("rubric_version", "metric_protocol"):
        if a_config.get(key) != b_config.get(key):
            invalid.append("EVALUATION_PROTOCOL_INCOMPATIBLE")
    if policy.comparison == "LEXICAL_ASR" and a_config.get("fixed_grading") != b_config.get(
        "fixed_grading"
    ):
        invalid.append("ISOLATED_ASR_CONFIGURATION_INCOMPATIBLE")
    count = len(samples)
    band_metrics = {}
    for label, evidence in (("baseline", left), ("candidate", right)):
        band_metrics[label] = {}
        for field in FIELDS:
            eligible = [s for s in samples if s.get("human", {}).get(field) is not None]
            band_metrics[label][field] = score_metrics(
                [s["human"][field] for s in eligible],
                [evidence.get(s["sample_id"], {}).get("ai", {}).get(field) for s in eligible],
            )
    metrics, matched_ids = [], {s["sample_id"] for s in samples}
    for threshold in policy.thresholds:
        name = threshold.metric
        a_values, b_values, pairs, common_a, common_b = [], [], [], [], []
        metric_ids = set()
        for sample in samples:
            a = _metric(left.get(sample["sample_id"]), sample, name)
            b = _metric(right.get(sample["sample_id"]), sample, name)
            if a is not None:
                a_values.append(a)
            if b is not None:
                b_values.append(b)
            if (
                a is not None
                and b is not None
                and left.get(sample["sample_id"], {}).get("available")
                and right.get(sample["sample_id"], {}).get("available")
            ):
                pairs.append(
                    (sample.get("candidate_id") or None, b - a if name in HIGHER_BETTER else a - b)
                )
                common_a.append(a)
                common_b.append(b)
                metric_ids.add(sample["sample_id"])
        matched_ids &= metric_ids
        # Error comparisons use exactly the same recordings on both sides.
        # Availability and request totals still retain the entire suite denominator.
        full_denominator = name in {
            "failure_rate",
            "score_coverage",
            "missing_overall_rate",
            "missing_artifact_count",
            "unknown_billing_attempts",
            "physical_requests",
            "provider_audio_ms",
            "cache_reuse_rate",
        }
        a_selected, b_selected = (a_values, b_values) if full_denominator else (common_a, common_b)
        a = mean(a_selected) if a_selected else None
        b = mean(b_selected) if b_selected else None
        if name == "signed_bias_abs":
            a, b = abs(a) if a is not None else None, abs(b) if b is not None else None
        if name in {
            "unknown_billing_attempts",
            "provider_audio_ms",
            "physical_requests",
            "missing_artifact_count",
        }:
            a, b = sum(a_values) if a_values else None, sum(b_values) if b_values else None
        difference = b - a if a is not None and b is not None else None
        regression = -difference if name in HIGHER_BETTER and difference is not None else difference
        state = (
            "INCONCLUSIVE"
            if regression is None
            else "FAIL"
            if regression > threshold.max_regression + 1e-12
            else "PASS"
        )
        if state == "FAIL":
            failed.append("METRIC_REGRESSION:" + name)
        if state == "INCONCLUSIVE":
            unavailable.append("METRIC_UNAVAILABLE:" + name)
        metrics.append(
            dict(
                metric=name,
                baseline=a,
                candidate=b,
                difference=difference,
                relative_difference=difference / abs(a) if difference is not None and a else None,
                tolerable_regression=threshold.max_regression,
                direction="HIGHER_BETTER" if name in HIGHER_BETTER else "LOWER_BETTER",
                status=state,
                baseline_coverage=len(a_values) / count if count else 0,
                candidate_coverage=len(b_values) / count if count else 0,
                paired=paired_difference(pairs)
                if name != "signed_bias_abs"
                else {
                    "ci95": None,
                    "ci_status": "NONLINEAR_ABSOLUTE_BIAS_INTERVAL_UNAVAILABLE",
                    "matched_samples": len(pairs),
                    "resampling_unit": "candidate",
                },
                aggregation="suite_total"
                if name
                in {
                    "unknown_billing_attempts",
                    "provider_audio_ms",
                    "physical_requests",
                    "missing_artifact_count",
                }
                else "macro_matched_recording_mean"
                if not full_denominator
                else "full_suite_recording_mean",
                matched_samples=len(metric_ids),
            )
        )
    # Availability is evaluated on the entire frozen denominator, not the favorable subset.
    required_fields = {t.metric[:-4] for t in policy.thresholds if t.metric.endswith("_mae")}
    if any(
        t.metric
        in {
            "exact_agreement",
            "within_0_5",
            "signed_bias_abs",
            "score_coverage",
            "missing_overall_rate",
        }
        for t in policy.thresholds
    ):
        required_fields.add("overall")

    def coverage(evidence):
        return (
            sum(
                bool(
                    (r := evidence.get(s["sample_id"]))
                    and r.get("available")
                    and all(r.get("ai", {}).get(field) is not None for field in required_fields)
                )
                for s in samples
            )
            / count
            if count
            else 0
        )

    a_coverage, b_coverage = coverage(left), coverage(right)
    if min(a_coverage, b_coverage) < policy.minimum_prediction_coverage:
        failed.append("PREDICTION_COVERAGE_BELOW_MINIMUM")
    if any(
        min(m["baseline_coverage"], m["candidate_coverage"]) < policy.minimum_reference_coverage
        for m in metrics
    ):
        failed.append("METRIC_REFERENCE_COVERAGE_BELOW_MINIMUM")
    if any(i["severity"] == "BLOCKED" for i in quality.get("issues", [])):
        failed.append("REQUIRED_DATASET_QUALITY_FAILED")
    for evidence in (baseline, candidate):
        if (
            sum(
                r.get("metrics", {}).get("unknown_billing_attempts", 0) or 0
                for r in evidence.get("rows", [])
            )
            > policy.max_unknown_billing_attempts
        ):
            failed.append("BILLING_RECONCILIATION_REQUIRED")
    speakers = {
        s.get("candidate_id")
        for s in samples
        if s["sample_id"] in matched_ids and s.get("candidate_id")
    }
    if len(speakers) < policy.minimum_independent_candidates:
        unavailable.append("INSUFFICIENT_MATCHED_INDEPENDENT_CANDIDATES")
    status = (
        "INVALID" if invalid else "FAIL" if failed else "INCONCLUSIVE" if unavailable else "PASS"
    )
    return dict(
        protocol=policy.protocol,
        status=status,
        selected_samples=count,
        matched_samples=len(matched_ids),
        matched_independent_candidates=len(speakers),
        baseline_coverage=a_coverage,
        candidate_coverage=b_coverage,
        metrics=metrics,
        band_metrics=band_metrics,
        reasons=sorted(set(invalid + failed + unavailable)),
        limitations=[
            "ENGINEERING_THRESHOLDS_NOT_STATISTICALLY_VALIDATED",
            "NO_CAUSAL_OR_SIGNIFICANCE_CLAIM",
            "CANDIDATE_PSEUDONYMS_REQUIRE_VERIFICATION",
            "NO_AUTOMATIC_MODEL_PROMOTION",
            "ASR_THRESHOLDS_USE_MACRO_RECORDING_MEANS",
        ],
    )
